<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { generateQRSVG } from './lib/qr';
  import { startStateStream, type AgentState } from './lib/state';
  import Unclaimed from './views/Unclaimed.svelte';
  import Ready from './views/Ready.svelte';
  import Booting from './views/Booting.svelte';
  import NetworkBadge from './views/NetworkBadge.svelte';

  let state: AgentState = $state({ view: 'BOOTING' });
  let qrSvg = $state<string>('');
  let qrSeed = $state<string>('');
  let stopStream: (() => void) | null = null;
  let now = $state(new Date());
  let clockTimer: number | null = null;

  onMount(() => {
    stopStream = startStateStream((s) => {
      state = s;
    });
    clockTimer = window.setInterval(() => { now = new Date(); }, 30_000);
  });

  onDestroy(() => {
    stopStream?.();
    if (clockTimer) clearInterval(clockTimer);
  });

  $effect(() => {
    const url = state.qr_url;
    if (url && url !== qrSeed) {
      qrSeed = url;
      generateQRSVG(url, 720).then((svg) => { qrSvg = svg; });
    }
  });

  function timeStr(d: Date) {
    return d.toLocaleTimeString('et-EE', { hour: '2-digit', minute: '2-digit' });
  }
</script>

<main class="relative flex h-full w-full flex-col overflow-hidden bg-slate-950 text-slate-100">
  <div class="pointer-events-none absolute inset-0">
    <div class="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-blue-600/30 blur-3xl"></div>
    <div class="absolute -bottom-40 right-0 h-80 w-80 rounded-full bg-violet-600/20 blur-3xl"></div>
  </div>

  <header class="relative z-10 flex items-center justify-between px-5 py-3">
    <div class="flex items-center gap-2">
      <div class="grid size-8 place-items-center rounded-lg bg-white text-slate-900">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="2"/>
          <path d="M3 12h18M12 3v18" stroke="currentColor" stroke-width="2"/>
        </svg>
      </div>
      <div class="text-sm font-semibold tracking-tight">Kohvrikapid</div>
    </div>
    <div class="flex items-center gap-2 text-[10px] text-slate-400">
      <NetworkBadge network={state.network} />
      <span class="font-mono">{timeStr(now)}</span>
    </div>
  </header>

  <div class="relative z-10 flex flex-1 items-center justify-center px-4 pb-4">
    {#if state.view === 'BOOTING'}
      <Booting />
    {:else if state.view === 'UNCLAIMED'}
      <Unclaimed {state} {qrSvg} />
    {:else if state.view === 'READY'}
      <Ready {state} />
    {/if}
  </div>
</main>
