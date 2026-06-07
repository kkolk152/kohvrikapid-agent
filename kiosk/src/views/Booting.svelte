<script lang="ts">
  import { onMount } from 'svelte';

  let lastFetch = $state<string>('—');
  let lastView = $state<string>('—');
  let lastError = $state<string>('—');
  let fetchCount = $state(0);

  onMount(() => {
    const tick = async () => {
      fetchCount += 1;
      lastFetch = new Date().toLocaleTimeString('et-EE');
      try {
        const r = await fetch('/api/state', { cache: 'no-store' });
        const data = await r.json();
        lastView = data.view ?? 'no-view';
      } catch (e) {
        lastError = String(e);
      }
      setTimeout(tick, 1500);
    };
    tick();
  });
</script>

<div class="flex h-full w-full flex-col items-center justify-center gap-6 p-6 text-center">
  <div class="size-12 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"></div>
  <div class="text-base font-medium text-slate-300">Käivitan…</div>

  <div class="mt-6 w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-left text-xs font-mono">
    <div class="mb-2 font-semibold uppercase text-amber-400">DEBUG</div>
    <div class="space-y-1 text-slate-300">
      <div>Fetch count: <span class="text-white">{fetchCount}</span></div>
      <div>Last fetch:  <span class="text-white">{lastFetch}</span></div>
      <div>Last view:   <span class="text-emerald-300">{lastView}</span></div>
      <div>Last error:  <span class="text-red-300">{lastError}</span></div>
    </div>
  </div>
</div>
