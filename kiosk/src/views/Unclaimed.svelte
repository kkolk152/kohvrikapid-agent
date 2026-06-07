<script lang="ts">
  import type { AgentState } from '../lib/state';

  let { state, qrSvg }: { state: AgentState; qrSvg: string } = $props();

  const rows = $derived(() => {
    const out: { label: string; value: string; mono?: boolean }[] = [];
    out.push({ label: 'Seerianumber', value: state.serial ?? '—', mono: true });
    const fw = state.firmware_version ? ` / fw ${state.firmware_version}` : '';
    out.push({ label: 'Tarkvara', value: `agent ${state.agent_version ?? '—'}${fw}` });
    if (state.network?.discovery_subnet) {
      out.push({ label: 'Võrk', value: state.network.discovery_subnet, mono: true });
    }
    return out;
  });
</script>

<div class="grid w-full max-w-md grid-rows-[auto_1fr_auto] gap-6 px-2 py-4">
  <div class="text-center">
    <div class="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-amber-300">
      <span class="size-1.5 animate-pulse rounded-full bg-amber-400"></span>
      Ootan sidumist
    </div>
    <h1 class="mt-4 text-3xl font-bold tracking-tight text-white">
      Skanni QR kood<br/>siduma kapiga
    </h1>
    <p class="mt-2 text-sm text-slate-400">
      Telefoniga skannides avaneb admin paneel kus saab valida platformi ja kapi.
    </p>
  </div>

  <div class="flex items-center justify-center">
    <div class="relative rounded-3xl border border-white/10 bg-white p-6 shadow-2xl shadow-blue-500/20">
      {#if qrSvg}
        <div class="size-80">
          {@html qrSvg}
        </div>
      {:else}
        <div class="grid size-80 place-items-center text-slate-400">
          <div class="size-12 animate-spin rounded-full border-4 border-slate-200 border-t-slate-500"></div>
        </div>
      {/if}
    </div>
  </div>

  <div class="space-y-2 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-xs">
    {#each rows() as row}
      <div class="flex items-center justify-between gap-3">
        <span class="text-slate-500">{row.label}</span>
        <span class="truncate {row.mono ? 'font-mono' : ''} text-slate-200">{row.value}</span>
      </div>
    {/each}
    {#if state.qr_label}
      <div class="border-t border-slate-800 pt-2 text-center text-[10px] text-slate-500">
        {state.qr_label}
      </div>
    {/if}
  </div>
</div>
