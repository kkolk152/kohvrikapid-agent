<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state, qrSvg }: { state: AgentState; qrSvg: string } = $props();
</script>

<!--
  Responsive layout — toimib nii portrait (720x1280) kui landscape (1280x720):
  - Landscape: kaks tulpa kõrvuti — info vasakul, QR paremal
  - Portrait: stacked vertikaalselt — info üleval, QR keskel/all
  Tailwind `lg:` breakpoint = 1024px, sobib eristamiseks.
-->

<div class="flex h-full w-full items-center justify-center p-6">
  <div class="grid h-full w-full max-w-6xl gap-6 lg:grid-cols-[1fr_auto] lg:items-center">

    <!-- VASAK / ÜLEMINE TULP: info -->
    <div class="flex flex-col items-center gap-5 text-center lg:items-start lg:text-left lg:pr-4">
      <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-amber-300">
        <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
        Ootan sidumist
      </div>

      <h1 class="text-3xl font-bold leading-[1.1] tracking-tight text-white lg:text-4xl">
        Skanni QR kood<br/>kapi sidumiseks
      </h1>

      <p class="max-w-md text-sm leading-relaxed text-slate-400 lg:text-base">
        Telefoniga skannides avaneb admin paneel, kus saab valida platformi ja kapi.
      </p>

      <!-- Info-kaart -->
      <div class="mt-2 w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur">
        <dl class="space-y-2 text-xs">
          <div class="flex items-center justify-between gap-3">
            <dt class="text-slate-500">Seerianumber</dt>
            <dd class="font-mono text-slate-200">{state.serial ?? '—'}</dd>
          </div>
          <div class="flex items-center justify-between gap-3">
            <dt class="text-slate-500">Tarkvara</dt>
            <dd class="font-mono text-slate-200">
              agent {state.agent_version ?? '—'}{state.firmware_version ? ` · fw ${state.firmware_version}` : ''}
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

    <!-- PAREM / ALUMINE TULP: QR kaart -->
    <div class="flex items-center justify-center">
      <div class="rounded-3xl bg-white p-5 shadow-2xl shadow-blue-500/20">
        {#if qrSvg}
          <div class="aspect-square w-[min(56vh,360px)]">
            {@html qrSvg}
          </div>
        {:else}
          <div class="grid aspect-square w-[min(56vh,360px)] place-items-center text-slate-400">
            <div class="size-12 animate-spin rounded-full border-4 border-slate-200 border-t-slate-500"></div>
          </div>
        {/if}
      </div>
    </div>
  </div>
</div>
