<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state, qrSvg }: { state: AgentState; qrSvg: string } = $props();
</script>

<div class="flex h-full w-full flex-col items-center justify-between gap-8 px-6 pb-8 pt-2">
  <!-- HEADING -->
  <div class="flex flex-col items-center gap-3 text-center">
    <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-amber-300">
      <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
      Ootan sidumist
    </div>
    <h1 class="text-2xl font-bold leading-tight tracking-tight text-white">
      Skanni QR kood<br/>siduma kapiga
    </h1>
  </div>

  <!-- QR CARD (suur, keskel, fookuses) -->
  <div class="flex w-full justify-center">
    <div class="rounded-3xl bg-white p-4 shadow-2xl shadow-blue-500/30">
      {#if qrSvg}
        <div class="size-[420px]">
          {@html qrSvg}
        </div>
      {:else}
        <div class="grid size-[420px] place-items-center text-slate-400">
          <div class="size-12 animate-spin rounded-full border-4 border-slate-200 border-t-slate-500"></div>
        </div>
      {/if}
    </div>
  </div>

  <!-- DETAILS CARD (all servas) -->
  <div class="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/70 p-4 backdrop-blur">
    <p class="mb-3 text-center text-xs leading-snug text-slate-400">
      Telefoniga skannides avaneb admin paneel kus saab valida platformi ja kapi.
    </p>
    <div class="space-y-1.5 border-t border-slate-800 pt-3 text-xs">
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-500">Seerianumber</span>
        <span class="font-mono text-slate-200">{state.serial ?? '—'}</span>
      </div>
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-500">Tarkvara</span>
        <span class="font-mono text-slate-200">
          agent {state.agent_version ?? '—'}{state.firmware_version ? ` / fw ${state.firmware_version}` : ''}
        </span>
      </div>
      {#if state.network?.discovery_subnet}
        <div class="flex items-center justify-between gap-3">
          <span class="text-slate-500">Võrk</span>
          <span class="font-mono text-slate-200">{state.network.discovery_subnet}</span>
        </div>
      {/if}
    </div>
  </div>
</div>
