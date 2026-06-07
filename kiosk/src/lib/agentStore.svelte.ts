import type { AgentState } from './state';

// Module-level shared reactive state — Svelte 5 ametlik muster
// (.svelte.ts laiend lubab $state kasutust väljaspool komponente)
export const agentState = $state<AgentState>({ view: 'BOOTING' });

let polling = false;

export function startAgentPolling(): void {
  if (polling) return;
  polling = true;

  const tick = async () => {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (r.ok) {
        const data = (await r.json()) as AgentState;
        // Otsene property omistamine $state proxy peal
        agentState.view = data.view ?? 'BOOTING';
        agentState.title = data.title;
        agentState.message = data.message;
        agentState.lines = data.lines;
        agentState.cabinet_name = data.cabinet_name;
        agentState.cabinet_kind = data.cabinet_kind;
        agentState.slot_status = data.slot_status;
        agentState.serial = data.serial;
        agentState.agent_version = data.agent_version;
        agentState.firmware_version = data.firmware_version;
        agentState.network = data.network;
        agentState.last_seen_at = data.last_seen_at;
      }
    } catch {
      // ignore — retry next tick
    }
    setTimeout(tick, 1000);
  };
  tick();
}
