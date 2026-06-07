<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state, qrSvg }: { state: AgentState; qrSvg: string } = $props();
</script>

<!-- Portrait 720x1280 — optimeeritud paigutus -->
<div class="flex h-full w-full max-w-md flex-col items-center justify-between gap-6 px-6 py-4">

  <!-- TIPP: status badge + title -->
  <div class="flex flex-col items-center gap-3 text-center">
    <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-amber-300">
      <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
      Ootan sidumist
    </div>
    <h1 class="text-2xl font-bold leading-tight tracking-tight text-white">
      Skanni QR kood<br/>kapi sidumiseks
    </h1>
  </div>

  <!-- KESK: QR kaart -->
  <div class="flex items-center justify-center">
    <div class="rounded-2xl bg-white p-4 shadow-2xl shadow-blue-500/30">
      {#if qrSvg}
        <div class="size-64">
          {@html qrSvg}
        </div>
      {:else}
        <div class="grid size-64 place-items-center text-slate-400">
          <div class="size-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-500"></div>
        </div>
      {/if}
    </div>
  </div>

  <!-- ALA: kirjeldus + info-kaart -->
  <div class="flex w-full flex-col gap-3">
    <p class="text-center text-sm leading-snug text-slate-400">
      Skanni telefoniga avaneb admin paneel platformi ja kapi valimiseks.
    </p>
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-xs backdrop-blur">
      <dl class="space-y-1.5">
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-500">Seerianumber</dt>
          <dd class="font-mono text-slate-200">{state.serial ?? '—'}</dd>
        </div>
        <div class="flex items-center justify-between gap-3">
          <dt class="text-slate-500">Tarkvara</dt>
          <dd class="font-mono text-slate-200">
            v{state.agent_version ?? '—'}
          </dd>
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
</div>
