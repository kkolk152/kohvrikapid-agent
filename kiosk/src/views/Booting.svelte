<script lang="ts">
  import { agentState } from '../lib/agentStore.svelte';
</script>

<div class="flex h-full w-full flex-col items-center justify-center gap-6 p-6 text-center">
  <div class="size-12 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"></div>
  <div class="text-base font-medium text-slate-300">Käivitan…</div>

  <!-- DEBUG: näita agentState reaalajas -->
  <div class="mt-6 w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-left text-xs font-mono">
    <div class="mb-2 font-semibold uppercase text-amber-400">DEBUG (agentState)</div>
    <div class="space-y-1 text-slate-300">
      <div>view: <span class="text-emerald-300">{agentState.view}</span></div>
      <div>cabinet_kind: <span class="text-emerald-300">{agentState.cabinet_kind ?? '—'}</span></div>
      <div>cabinet_name: <span class="text-emerald-300">{agentState.cabinet_name ?? '—'}</span></div>
      <div>serial: <span class="text-white">{agentState.serial ?? '—'}</span></div>
    </div>
  </div>
</div>
