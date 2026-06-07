import { writable, type Writable } from 'svelte/store';
import type { AgentState } from './state';

export const agentState: Writable<AgentState> = writable({ view: 'BOOTING' });

export const debug: Writable<{
  startCount: number;
  tickCount: number;
  lastTickAt: string;
  lastView: string;
  lastError: string;
}> = writable({
  startCount: 0,
  tickCount: 0,
  lastTickAt: '',
  lastView: '',
  lastError: '',
});

let polling = false;

export function startAgentPolling(): void {
  debug.update((d) => ({ ...d, startCount: d.startCount + 1 }));
  if (polling) return;
  polling = true;

  const tick = async () => {
    debug.update((d) => ({
      ...d,
      tickCount: d.tickCount + 1,
      lastTickAt: new Date().toLocaleTimeString('et-EE'),
    }));
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) {
        debug.update((d) => ({ ...d, lastError: `HTTP ${r.status}` }));
        setTimeout(tick, 1000);
        return;
      }
      const data = (await r.json()) as AgentState;
      debug.update((d) => ({ ...d, lastView: data.view ?? 'no-view', lastError: '' }));
      agentState.set(data);
    } catch (e) {
      debug.update((d) => ({ ...d, lastError: String(e) }));
    }
    setTimeout(tick, 1000);
  };
  tick();
}
