<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state, qrSvg }: { state: AgentState; qrSvg: string } = $props();
</script>

<!--
  Responsive: portrait (720w) ja landscape (1280w) töötavad mõlemad.
  Breakpoint @ 900px: laiem ekraan -> info+QR kõrvuti, kitsam -> stacked.
-->

<style>
  .qr-portrait { width: 13rem; height: 13rem; }
  @media (min-width: 900px) {
    .layout { flex-direction: row; gap: 3rem; align-items: center; text-align: left; }
    .info-col { align-items: flex-start; max-width: 28rem; }
    .qr-portrait { width: 17rem; height: 17rem; }
  }
</style>

<div class="layout flex h-full w-full max-w-5xl flex-col items-center justify-center gap-5 px-6 py-3">

  <!-- INFO TULP -->
  <div class="info-col flex flex-col items-center gap-3 text-center">
    <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-amber-300">
      <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
      Ootan sidumist
    </div>
    <h1 class="text-2xl font-bold leading-tight tracking-tight text-white">
      Skanni QR kood<br/>kapi sidumiseks
    </h1>
    <p class="max-w-xs text-sm leading-snug text-slate-400">
      Skanni telefoniga, avaneb admin paneel.
    </p>
    <div class="mt-1 w-full max-w-xs rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-[11px] backdrop-blur">
      <dl class="space-y-1">
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-500">Serial</dt>
          <dd class="font-mono text-slate-200">{state.serial ?? '—'}</dd>
        </div>
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-500">Versioon</dt>
          <dd class="font-mono text-slate-200">v{state.agent_version ?? '—'}</dd>
        </div>
        {#if state.network?.discovery_subnet}
          <div class="flex items-center justify-between gap-3">
            <dt class="text-slate-500">Võrk</dt>
            <dd class="font-mono text-slate-200">{state.network.discovery_subnet}</dd>
          </div>
        {/if}
      </dl>
    </div>
  </div>

  <!-- QR TULP -->
  <div class="flex shrink-0 items-center justify-center">
    <div class="rounded-2xl bg-white p-3 shadow-2xl shadow-blue-500/30">
      {#if qrSvg}
        <div class="qr-portrait">
          {@html qrSvg}
        </div>
      {:else}
        <div class="qr-portrait grid place-items-center text-slate-400">
          <div class="size-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-500"></div>
        </div>
      {/if}
    </div>
  </div>
</div>
