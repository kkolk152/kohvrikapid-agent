<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state }: { state: AgentState } = $props();
</script>

<div class="flex h-full w-full max-w-2xl flex-col items-center justify-center gap-6 px-6 py-4 text-center">

  <!-- Status badge -->
  <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-widest text-amber-300">
    <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
    Ootan sidumist
  </div>

  <!-- Title -->
  <div class="space-y-3">
    <h1 class="text-3xl font-bold leading-tight tracking-tight text-white sm:text-4xl">
      See seade pole<br/>veel seotud
    </h1>
    <p class="text-base leading-snug text-slate-400">
      Administraator peab admin paneelist<br/>seda kontrollerit kapiga siduma.
    </p>
  </div>

  <!-- Serial number — big and prominent -->
  <div class="space-y-1 rounded-2xl border border-blue-500/30 bg-blue-500/5 px-6 py-4">
    <div class="text-xs font-medium uppercase tracking-widest text-blue-300">Seerianumber</div>
    <div class="font-mono text-xl font-semibold text-white sm:text-2xl">{state.serial ?? '—'}</div>
  </div>

  <!-- Info pillid -->
  <div class="flex flex-wrap justify-center gap-2 text-xs">
    <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-slate-300">
      <span class="text-slate-500">Versioon</span>
      <span class="font-mono text-slate-100">v{state.agent_version ?? '—'}</span>
    </span>
    {#if state.network?.discovery_subnet}
      <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-slate-300">
        <span class="text-slate-500">Võrk</span>
        <span class="font-mono text-slate-100">{state.network.discovery_subnet}</span>
      </span>
    {/if}
  </div>
</div>
