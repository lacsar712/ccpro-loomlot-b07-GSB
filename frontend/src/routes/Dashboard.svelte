<script>
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { api } from '../lib/api.js';

  let stats = null;
  let error = '';

  onMount(async () => {
    try {
      stats = await api('/dashboard/stats');
    } catch (e) {
      error = e.message;
    }
  });
</script>

<h1 class="page-title">工艺总览</h1>
<p class="page-sub">按染坊 → 染缸 → 染程 → 色牢度推进；顶部步骤条可跳转各工序。</p>

{#if error}
  <p class="err">{error}</p>
{/if}

{#if stats}
  <div class="grid-stats">
    <div class="stat">
      <div class="n">{stats.dyeHouseTotal}</div>
      <div class="l">染坊</div>
    </div>
    <div class="stat">
      <div class="n">{stats.vatReadyCount}</div>
      <div class="l">就绪染缸</div>
    </div>
    <div class="stat">
      <div class="n">{stats.vatDyeingCount}</div>
      <div class="l">染程中</div>
    </div>
    <div class="stat">
      <div class="n">{stats.vatDrainCount}</div>
      <div class="l">排液染缸</div>
    </div>
    <div class="stat">
      <div class="n">{stats.lotsLast7d}</div>
      <div class="l">近 7 日染程</div>
    </div>
    <div class="stat">
      <div class="n">{stats.checksLast24h}</div>
      <div class="l">近 24 时抽检</div>
    </div>
  </div>
{/if}

<div class="panel">
  <p style="margin:0 0 0.75rem;color:var(--indigo-mist);font-size:0.9rem;">
    业务约束：就绪 ⇄ 染程中 → 排液 → 就绪。开染程自动入染程中；排液回到就绪前须先处理完该缸染程，非法跳跃返回 409。
  </p>
  <div class="toolbar">
    <a class="btn" href="/houses" use:link>进入染坊</a>
    <a class="btn ghost" href="/vats" use:link>管理染缸</a>
    <a class="btn ghost" href="/lots" use:link>登记染程</a>
    <a class="btn ghost" href="/checks" use:link>色牢度抽检</a>
  </div>
</div>
