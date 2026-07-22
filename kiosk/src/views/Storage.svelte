<script lang="ts">
  import type { AgentState, SlotInfo } from '../lib/state';
  import { verifyStoragePin, startStorage, buildSlots } from '../lib/state';

  let { state }: { state: AgentState } = $props();

  type Mode = 'home' | 'deposit' | 'retrieve';
  type Phase = 'idle' | 'busy' | 'opening' | 'success' | 'error';

  let mode = $state<Mode>('home');
  let phase = $state<Phase>('idle');
  let pin = $state<string>('');
  let slotCode = $state<string>('');
  let issuedPin = $state<string>('');
  let errorMsg = $state<string>('');
  let resetTimer: number | null = null;

  const MAX_PIN_LENGTH = 6;
  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];
  const pinSlots = [0, 1, 2, 3, 4, 5];

  const slots = $derived<SlotInfo[]>(buildSlots(state));
  const freeCount = $derived(slots.filter((s) => !s.occupied).length);

  const SIZE_COLOR: Record<string, string> = {
    S: 'from-sky-500 to-sky-600',
    M: 'from-emerald-500 to-emerald-600',
    L: 'from-amber-500 to-amber-600',
    XL: 'from-violet-500 to-violet-600',
  };

  function go(m: Mode) {
    clearReset();
    mode = m;
    phase = 'idle';
    pin = '';
    slotCode = '';
    issuedPin = '';
    errorMsg = '';
  }

  function clearReset() {
    if (resetTimer) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
  }

  function scheduleHome(ms: number) {
    clearReset();
    resetTimer = window.setTimeout(() => go('home'), ms);
  }

  // ---- HOIUSTA ----
  async function deposit(slot: SlotInfo) {
    if (phase === 'busy' || slot.occupied) return;
    phase = 'busy';
    errorMsg = '';
    try {
      const r = await startStorage({ slot_code: slot.code });
      if (r.ok && r.slot_code) {
        slotCode = r.slot_code;
        issuedPin = r.pin ?? '';
        phase = 'opening';
        setTimeout(() => {
          if (phase === 'opening') phase = 'success';
        }, 2500);
        scheduleHome(30_000);
      } else {
        errorMsg = errorMessage(r.error);
        phase = 'error';
        scheduleHome(5_000);
      }
    } catch {
      errorMsg = 'Võrgu viga';
      phase = 'error';
      scheduleHome(5_000);
    }
  }

  // ---- VÕTA VÄLJA (PIN) ----
  function pressDigit(d: string) {
    if (phase !== 'idle' || pin.length >= MAX_PIN_LENGTH) return;
    pin = pin + d;
    if (pin.length === MAX_PIN_LENGTH) submitPin();
  }
  function pressBackspace() {
    if (phase !== 'idle') return;
    pin = pin.slice(0, -1);
  }
  function pressClear() {
    if (phase === 'error') {
      errorMsg = '';
      phase = 'idle';
    }
    pin = '';
  }

  async function submitPin() {
    if (pin.length < 3) return;
    phase = 'busy';
    errorMsg = '';
    try {
      const r = await verifyStoragePin(pin);
      if (r.ok && r.slot_code) {
        slotCode = r.slot_code;
        phase = 'opening';
        setTimeout(() => {
          if (phase === 'opening') phase = 'success';
        }, 2500);
        scheduleHome(12_000);
      } else {
        errorMsg = errorMessage(r.error);
        phase = 'error';
        pin = '';
      }
    } catch {
      errorMsg = 'Võrgu viga';
      phase = 'error';
      pin = '';
    }
  }

  function errorMessage(code?: string): string {
    switch (code) {
      case 'invalid_pin': return 'Vale PIN';
      case 'no_free_slot': return 'Vabu luuke pole';
      case 'slot_taken': return 'Luuk on hõivatud';
      case 'device_not_paired': return 'Seade pole seotud';
      case 'cabinet_not_found': return 'Kapp puudub';
      case 'not_storage_cabinet': return 'Pole hoiukapp';
      default: return code ?? 'Tundmatu viga';
    }
  }
</script>

<!-- ============ AVALEHT ============ -->
{#if mode === 'home'}
  <div class="flex h-full w-full max-w-xl flex-col items-center justify-center gap-8 px-4 py-6 text-center">
    <div>
      <h1 class="text-4xl font-bold tracking-tight text-white">{state.cabinet_name ?? 'Hoiukapp'}</h1>
      <p class="mt-2 text-base text-slate-400">Turvaline pagasi hoidmine</p>
      <p class="mt-1 text-sm text-slate-500">{freeCount} vaba / {slots.length} luuki</p>
    </div>
    <div class="grid w-full gap-4">
      <button
        onclick={() => go('deposit')}
        disabled={freeCount === 0}
        class="group flex items-center gap-4 rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 px-6 py-6 text-left shadow-2xl shadow-emerald-500/30 transition active:scale-[0.98] disabled:opacity-40"
      >
        <div class="grid size-14 shrink-0 place-items-center rounded-xl bg-white/20">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="white" stroke-width="3" stroke-linecap="round"/></svg>
        </div>
        <div>
          <div class="text-2xl font-bold text-white">Hoiusta pagas</div>
          <div class="text-sm text-white/80">Vali luuk ja pane asjad sisse</div>
        </div>
      </button>
      <button
        onclick={() => go('retrieve')}
        class="group flex items-center gap-4 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 px-6 py-6 text-left shadow-2xl shadow-blue-500/30 transition active:scale-[0.98]"
      >
        <div class="grid size-14 shrink-0 place-items-center rounded-xl bg-white/20">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div>
          <div class="text-2xl font-bold text-white">Võta pagas välja</div>
          <div class="text-sm text-white/80">Sisesta PIN</div>
        </div>
      </button>
    </div>
  </div>

<!-- ============ HOIUSTA: vali luuk ============ -->
{:else if mode === 'deposit' && (phase === 'idle' || phase === 'busy')}
  <div class="flex h-full w-full max-w-xl flex-col gap-4 px-4 py-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold text-white">Vali vaba luuk</h1>
      <button onclick={() => go('home')} class="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300">Tagasi</button>
    </div>
    <p class="text-sm text-slate-400">Puuduta vaba luuki (suurus tähisel). Hõivatud luuke ei saa valida.</p>
    <div class="grid grid-cols-4 gap-2.5 overflow-y-auto sm:grid-cols-5">
      {#each slots as s}
        <button
          onclick={() => deposit(s)}
          disabled={s.occupied || phase === 'busy'}
          class={
            'flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border text-white transition active:scale-95 ' +
            (s.occupied
              ? 'cursor-not-allowed border-slate-800 bg-slate-900/40 text-slate-600'
              : 'border-transparent bg-gradient-to-br ' + (SIZE_COLOR[s.size] ?? SIZE_COLOR.M) + ' shadow-lg')
          }
        >
          <span class="text-lg font-bold">{s.number}</span>
          <span class="text-xs font-semibold opacity-90">{s.occupied ? '—' : s.size}</span>
        </button>
      {/each}
    </div>
    {#if phase === 'busy'}
      <div class="text-center text-sm text-slate-400">Loon sessiooni…</div>
    {/if}
  </div>

<!-- ============ VÕTA VÄLJA: PIN ============ -->
{:else if mode === 'retrieve' && (phase === 'idle' || phase === 'busy' || phase === 'error')}
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-5 px-4 py-4">
    <div class="flex w-full items-center justify-between">
      <button onclick={() => go('home')} class="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300">← Tagasi</button>
      <span class="text-sm font-semibold text-slate-300">{state.cabinet_name ?? 'Hoiukapp'}</span>
    </div>
    <h1 class="text-2xl font-bold text-white">Sisesta PIN</h1>
    <div class="flex items-center justify-center gap-3">
      {#each pinSlots as i}
        <div class={'grid size-12 place-items-center rounded-xl border text-2xl font-bold ' + (i < pin.length ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 bg-slate-900/60 text-slate-600')}>
          {i < pin.length ? '●' : ''}
        </div>
      {/each}
    </div>
    {#if phase === 'busy'}
      <div class="text-sm text-slate-400">Kontrollin…</div>
    {:else if phase === 'error'}
      <div class="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-300">{errorMsg}</div>
    {/if}
    <div class="grid w-full grid-cols-3 gap-2.5">
      {#each keys as k}
        <button onclick={() => pressDigit(k)} disabled={phase === 'busy'} class="h-14 rounded-xl border border-slate-700 bg-slate-900/60 text-2xl font-bold text-white transition active:scale-95 disabled:opacity-50">{k}</button>
      {/each}
      <button onclick={pressClear} class="h-14 rounded-xl border border-slate-700 bg-slate-900/40 text-xs font-semibold uppercase text-slate-400 transition active:scale-95">Tühjenda</button>
      <button onclick={() => pressDigit('0')} disabled={phase === 'busy'} class="h-14 rounded-xl border border-slate-700 bg-slate-900/60 text-2xl font-bold text-white transition active:scale-95 disabled:opacity-50">0</button>
      <button onclick={pressBackspace} disabled={phase === 'busy'} class="h-14 rounded-xl border border-slate-700 bg-slate-900/40 text-xl font-bold text-slate-300 transition active:scale-95 disabled:opacity-50">←</button>
    </div>
  </div>

<!-- ============ AVAB LUUGI ============ -->
{:else if phase === 'opening'}
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-6 px-4 text-center">
    <div class="size-24 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"></div>
    <h1 class="text-3xl font-bold text-white">Avab luugi {slotCode}</h1>
    {#if issuedPin}
      <div class="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-6 py-4">
        <div class="text-xs uppercase tracking-widest text-emerald-300/80">Sinu PIN</div>
        <div class="font-mono text-4xl font-bold tracking-[0.3em] text-white">{issuedPin}</div>
      </div>
      <p class="text-sm text-slate-400">Jäta PIN meelde — sellega võtad asjad hiljem välja.</p>
    {:else}
      <p class="text-sm text-slate-400">Palun oota…</p>
    {/if}
  </div>

<!-- ============ VALMIS ============ -->
{:else if phase === 'success'}
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-6 px-4 text-center">
    <div class="grid size-28 place-items-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600 shadow-2xl shadow-emerald-500/40">
      <svg width="60" height="60" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
    <h1 class="text-3xl font-bold text-white">Luuk {slotCode} on avatud</h1>
    {#if issuedPin}
      <div class="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-6 py-3">
        <div class="text-xs uppercase tracking-widest text-emerald-300/80">PIN</div>
        <div class="font-mono text-3xl font-bold tracking-[0.3em] text-white">{issuedPin}</div>
      </div>
      <p class="text-sm text-slate-400">Pane asjad sisse ja sulge luuk. Jäta PIN meelde.</p>
    {:else}
      <p class="text-sm text-slate-400">Võta ese ja sulge luuk.</p>
    {/if}
    <button onclick={() => go('home')} class="rounded-xl border border-slate-700 px-6 py-2.5 text-sm font-semibold text-slate-200">Valmis</button>
  </div>

{:else if phase === 'error'}
  <div class="flex h-full w-full max-w-sm flex-col items-center justify-center gap-5 px-4 text-center">
    <div class="rounded-lg border border-red-500/40 bg-red-500/10 px-5 py-3 text-base font-medium text-red-300">{errorMsg}</div>
    <button onclick={() => go('home')} class="rounded-xl border border-slate-700 px-6 py-2.5 text-sm font-semibold text-slate-200">Tagasi</button>
  </div>
{/if}
