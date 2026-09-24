<script>
  import { onMount } from 'svelte';
  import { api, VAT_STATUS } from '../lib/api.js';

  let houses = [];
  let rows = [];
  let error = '';
  let form = {
    dyeHouseId: '',
    vatCode: '',
    fiberType: '棉',
    capacityL: 500,
    status: 'ready',
  };
  let editing = null;

  async function load() {
    error = '';
    try {
      [houses, rows] = await Promise.all([api('/dye-houses'), api('/vats')]);
      if (!form.dyeHouseId && houses.length) form.dyeHouseId = String(houses[0].id);
    } catch (e) {
      error = e.message;
    }
  }

  onMount(load);

  function houseName(id) {
    return houses.find((h) => h.id === id)?.name || id;
  }

  async function save() {
    error = '';
    try {
      const body = {
        dyeHouseId: Number(form.dyeHouseId),
        vatCode: form.vatCode.trim(),
        fiberType: form.fiberType.trim(),
        capacityL: Number(form.capacityL),
        status: form.status,
      };
      if (editing) {
        await api(`/vats/${editing}`, { method: 'PUT', body: JSON.stringify(body) });
      } else {
        await api('/vats', { method: 'POST', body: JSON.stringify(body) });
      }
      editing = null;
      form = {
        dyeHouseId: form.dyeHouseId,
        vatCode: '',
        fiberType: '棉',
        capacityL: 500,
        status: 'ready',
      };
      await load();
    } catch (e) {
      error = e.message;
    }
  }

  function startEdit(row) {
    editing = row.id;
    form = {
      dyeHouseId: String(row.dyeHouseId),
      vatCode: row.vatCode,
      fiberType: row.fiberType,
      capacityL: row.capacityL,
      status: row.status,
    };
  }

  // 唯一的状态迁移动作：排液走专用排液口，其余走手工改状态，
  // 后端三条路径共用同一迁移判定。
  async function transition(row, target) {
    error = '';
    try {
      if (target === 'drain') {
        await api(`/vats/${row.id}/drain`, { method: 'POST' });
      } else {
        await api(`/vats/${row.id}`, {
          method: 'PUT',
          body: JSON.stringify({ status: target }),
        });
      }
      await load();
    } catch (e) {
      error = e.message;
    }
  }

  async function remove(id) {
    if (!confirm('确认删除该染缸？')) return;
    error = '';
    try {
      await api(`/vats/${id}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      error = e.message;
    }
  }
</script>

<h1 class="page-title">染缸</h1>
<p class="page-sub">就绪 ⇄ 染程中 → 排液 → 就绪。排液回到就绪前须先处理完该缸染程。容量单位为升。</p>

<div class="panel" style="margin-bottom:1rem;">
  <div class="form-grid">
    <label
      >所属染坊
      <select bind:value={form.dyeHouseId}>
        {#each houses as h}
          <option value={String(h.id)}>{h.name}</option>
        {/each}
      </select>
    </label>
    <label>缸号 <input bind:value={form.vatCode} /></label>
    <label>纤维类型 <input bind:value={form.fiberType} /></label>
    <label>容量 (L) <input type="number" step="0.1" bind:value={form.capacityL} /></label>
    <label
      >状态
      <select bind:value={form.status}>
        {#if editing}
          {@const cur = rows.find((r) => r.id === editing)}
          <option value={cur.status}>{VAT_STATUS[cur.status] || cur.status}（当前）</option>
          {#each (cur.nextStatuses || []) as next}
            <option value={next}>{VAT_STATUS[next] || next}</option>
          {/each}
        {:else}
          <option value="ready">就绪</option>
          <option value="dyeing">染色中</option>
          <option value="drain">排液</option>
        {/if}
      </select>
    </label>
  </div>
  <div class="toolbar">
    <button class="btn" type="button" on:click={save}>{editing ? '保存修改' : '新建染缸'}</button>
    {#if editing}
      <button
        class="btn ghost"
        type="button"
        on:click={() => {
          editing = null;
        }}>取消</button
      >
    {/if}
  </div>
  {#if error}<p class="err">{error}</p>{/if}
</div>

<div class="panel">
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>染坊</th>
        <th>缸号</th>
        <th>纤维</th>
        <th>容量 L</th>
        <th>状态</th>
        <th>允许的下一状态</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each rows as row}
        <tr>
          <td>{row.id}</td>
          <td>{houseName(row.dyeHouseId)}</td>
          <td>{row.vatCode}</td>
          <td>{row.fiberType}</td>
          <td>{row.capacityL}</td>
          <td><span class="badge {row.status}">{VAT_STATUS[row.status] || row.status}</span></td>
          <td>
            {#each row.nextStatuses || [] as next}
              <button
                class="btn ghost small"
                type="button"
                on:click={() => transition(row, next)}
                title="迁移到该状态"
              >
                → {VAT_STATUS[next] || next}
              </button>
            {/each}
          </td>
          <td class="row-actions">
            <button class="btn ghost small" type="button" on:click={() => startEdit(row)}>编辑</button>
            <button class="btn danger small" type="button" on:click={() => remove(row.id)}>删除</button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
