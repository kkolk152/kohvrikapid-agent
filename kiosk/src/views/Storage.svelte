<script lang="ts">
  import type { AgentState } from '../lib/state';
  import { verifyStoragePin } from '../lib/state';

  let { state }: { state: AgentState } = $props();

  type Phase = 'idle' | 'verifying' | 'opening' | 'success' | 'error';

  let pin = $state<string>('');
  let phase = $state<Phase>('idle');
  let slotCode = $state<string>('');
  let errorMsg = $state<string>('');
  let resetTimer: number | null = null;

  const MAX_PIN_LENGTH = 6;

  function pressDigit(d: string) {
    if (phase !== 'idle' || pin.length >= MAX_PIN_LENGTH) return;
    pin = pin + d;
    if (pin.length === MAX_PIN_LENGTH) {
      submit();
    }
  }

  function pressBackspace() {
    if (phase !== 'idle') return;
    pin = pin.slice(0, -1);
  }

  function pressClear() {
    if (phase === 'idle') {
      pin = '';
    } else if (phase === 'error') {
      pin = '';
      phase = 'idle';
      errorMsg = '';
    }
  }

  async function submit() {
    if (pin.length < 3) return;
    phase = 'verifying';
    errorMsg = '';
    try {
      const r = await verifyStoragePin(pin);
      if (r.ok && r.slot_code) {
        slotCode = r.slot_code;
        phase = 'opening';
        scheduleReset(12_000);
        setTimeout(() => {
          if (phase === 'opening') phase = 'success';
        }, 2500);
      } else {
        errorMsg = errorMessage(r.error);
        phase = 'error';
        scheduleReset(4_000);
      }
    } catch {
      errorMsg = 'Võrgu viga';
      phase = 'error';
      scheduleReset(4_000);
    }
  }

  function scheduleReset(ms: number) {
    if (resetTimer) clearTimeout(resetTimer);
    resetTimer = window.setTimeout(() => {
      pin = '';
      slotCode = '';
      errorMsg = '';
      phase = 'idle';
      resetTimer = null;
    }, ms);
  }

  function errorMessage(code?: string): string {
    switch (code) {
      case 'invalid_pin': return 'Vale PIN';
      case 'device_not_paired': return 'Seade pole seotud';
      case 'cabinet_not_found': return 'Kapp puudub';
      case 'not_storage_cabinet': return 'Pole hoiukapp';
      default: return code ?? 'Tundmatu viga';
    }
  }

  const keys = ['1','2','3','4','5','6','7','8','9'];
  const pinSlots = [0, 1, 2, 3, 4, 5];
</script>

{#if phase === 'idle' || phase === 'verifying' || phase === 'error'}
  <!-- IDLE / VERIFYING / ERROR — PIN keypad ekraan -->
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-6 px-4 py-4">
    <div class="text-center">
      <div class="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-emerald-300">
        <span class="size-1.5 rounded-full bg-emerald-400"></span>
        {state.cabinet_name ?? 'Hoiukapp'}
      </div>
      <h1 class="mt-3 text-2xl font-bold text-white">Sisesta PIN</h1>
      <p class="mt-1 text-sm text-slate-400">Avab sinu luugi</p>
    </div>

    <!-- PIN display -->
    <div class="flex items-center justify-center gap-3">
      {#each pinSlots as i}
        <div
          class={
            "grid size-12 place-items-center rounded-xl border text-2xl font-bold transition-all " +
            (i < pin.length
              ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300'
              : 'border-slate-700 bg-slate-900/60 text-slate-600')
          }
        >
          {i < pin.length ? '●' : ''}
        </div>
      {/each}
    </div>

    {#if phase === 'verifying'}
      <div class="text-sm text-slate-400">Kontrollin…</div>
    {:else if phase === 'error'}
      <div class="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-300">
        {errorMsg}
      </div>
    {/if}

    <!-- Keypad -->
    <div class="grid w-full grid-cols-3 gap-2.5">
      {#each keys as k}
        <button
          onclick={() => pressDigit(k)}
          disabled={phase !== 'idle'}
          class="h-14 rounded-xl border border-slate-700 bg-slate-900/60 text-2xl font-bold text-white shadow-lg shadow-slate-950/40 transition active:scale-95 active:bg-slate-800 disabled:opacity-50"
        >
          {k}
        </button>
      {/each}
      <button
        onclick={pressClear}
        class="h-14 rounded-xl border border-slate-700 bg-slate-900/40 text-xs font-semibold uppercase tracking-wider text-slate-400 transition active:scale-95"
      >
        Tühjenda
      </button>
      <button
        onclick={() => pressDigit('0')}
        disabled={phase !== 'idle'}
        class="h-14 rounded-xl border border-slate-700 bg-slate-900/60 text-2xl font-bold text-white shadow-lg shadow-slate-950/40 transition active:scale-95 active:bg-slate-800 disabled:opacity-50"
      >
        0
      </button>
      <button
        onclick={pressBackspace}
        disabled={phase !== 'idle'}
        class="h-14 rounded-xl border border-slate-700 bg-slate-900/40 text-xl font-bold text-slate-300 transition active:scale-95 disabled:opacity-50"
      >
        ←
      </button>
    </div>
  </div>

{:else if phase === 'opening'}
  <!-- OPENING — animatsioon -->
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-6 px-4 py-4 text-center">
    <div class="size-24 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"></div>
    <div>
      <h1 class="text-3xl font-bold text-white">Avab luugi {slotCode}</h1>
      <p class="mt-2 text-sm text-slate-400">Palun oota…</p>
    </div>
  </div>

{:else if phase === 'success'}
  <!-- SUCCESS — luuk avatud -->
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-6 px-4 py-4 text-center">
    <div class="grid size-28 place-items-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600 shadow-2xl shadow-emerald-500/40">
      <svg width="60" height="60" viewBox="0 0 24 24" fill="none">
        <path d="M5 12l5 5L20 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div>
      <h1 class="text-3xl font-bold text-white">Luuk {slotCode} on avatud</h1>
      <p class="mt-2 text-sm text-slate-400">Võta ese ja sulge luuk</p>
    </div>
  </div>
{/if}
