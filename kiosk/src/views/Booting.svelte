<script lang="ts">
  import { agentState, debug } from '../lib/agentStore.svelte';
</script>

<div class="flex h-full w-full flex-col items-center justify-center gap-6 p-6 text-center">
  <div class="size-12 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"></div>
  <div class="text-base font-medium text-slate-300">Käivitan…</div>

  <div class="mt-6 w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-left text-xs font-mono">
    <div class="mb-2 font-semibold uppercase text-amber-400">DEBUG</div>
    <div class="space-y-1 text-slate-300">
      <div>startCount: <span class="text-white">{debug.startCount}</span></div>
      <div>tickCount:  <span class="text-white">{debug.tickCount}</span></div>
      <div>lastTickAt: <span class="text-white">{debug.lastTickAt || '—'}</span></div>
      <div>lastView:   <span class="text-emerald-300">{debug.lastView || '—'}</span></div>
      <div>lastError:  <span class="text-red-300">{debug.lastError || '—'}</span></div>
      <div class="mt-2 border-t border-slate-700 pt-2">
        <div>agentState.view: <span class="text-emerald-300">{agentState.view}</span></div>
        <div>agentState.kind: <span class="text-emerald-300">{agentState.cabinet_kind ?? '—'}</span></div>
      </div>
    </div>
  </div>
</div>
