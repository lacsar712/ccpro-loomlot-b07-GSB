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
        // 编辑表单不带状态，改状态一律走下方「下一状态」按钮，确保经过统一迁移判定。
        const { status, ...rest } = body;
        await api(`/vats/${editing}`, { method: 'PUT', body: JSON.stringify(rest) });
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

  // 手工改状态路径：PUT /vats/{id}
  async function changeStatus(row, target) {
    error = '';
    try {
      await api(`/vats/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: target }),
      });
      await load();
    } catch (e) {
      error = e.message;
    }
  }

  // 排液口路径：POST /vats/{id}/drain（染程中 → 排液）
  async function drain(row) {
    error = '';
    try {
      await api(`/vats/${row.id}/drain`, { method: 'POST' });
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
<p class="page-sub">
  状态迁移：就绪 ⇄ 染程中 → 排液 → 就绪；排液回就绪前须先处理染程。每行列出当前允许的下一状态。
</p>

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
    {#if !editing}
      <label
        >初始状态
        <select bind:value={form.status}>
          <option value="ready">就绪</option>
          <option value="dyeing">染程中</option>
          <option value="drain">排液</option>
        </select>
      </label>
    {/if}
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
          <td class="next-states">
            {#each row.allowedNextStatuses || [] as next}
              {#if next === 'drain'}
                <button class="btn ghost small" type="button" on:click={() => drain(row)}>
                  → {VAT_STATUS[next]}
                </button>
              {:else}
                <button class="btn ghost small" type="button" on:click={() => changeStatus(row, next)}>
                  → {VAT_STATUS[next]}
                </button>
              {/if}
            {/each}
            {#if !(row.allowedNextStatuses && row.allowedNextStatuses.length)}
              <span class="muted">—</span>
            {/if}
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

<style>
  .next-states {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
  }

  .muted {
    color: var(--indigo-mist);
    font-size: 0.85rem;
  }
</style>
