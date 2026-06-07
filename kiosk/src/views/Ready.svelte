<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state }: { state: AgentState } = $props();

  const kindLabel: Record<string, string> = {
    vending: 'Müügikapp',
    rental: 'Rendikapp',
    storage: 'Hoiukapp',
    parcel: 'Pakikapp',
    charging: 'Laadimiskapp',
  };
</script>

<div class="grid w-full max-w-md gap-6 px-2 py-4 text-center">
  <div class="space-y-2">
    <div class="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-emerald-300">
      <span class="size-1.5 rounded-full bg-emerald-400"></span>
      Valmis
    </div>
    <h1 class="text-4xl font-bold tracking-tight text-white">
      {state.cabinet_name ?? 'Kohvrikapp'}
    </h1>
    <div class="text-sm text-slate-400">
      {state.cabinet_kind ? kindLabel[state.cabinet_kind] ?? state.cabinet_kind : ''}
    </div>
  </div>

  <div class="grid place-items-center py-12">
    <div class="grid size-40 place-items-center rounded-full bg-gradient-to-br from-blue-500 to-violet-600 shadow-2xl shadow-blue-500/30">
      <svg width="80" height="80" viewBox="0 0 24 24" fill="none">
        <path d="M5 12l5 5L20 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
  </div>

  <p class="text-base text-slate-300">
    Tere tulemast!
  </p>
</div>
