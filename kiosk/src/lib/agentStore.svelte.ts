import type { AgentState } from './state';

export const agentState = $state<AgentState>({ view: 'BOOTING' });

// DEBUG state — näeb Booting view-l et tuvastada polling probleemi
export const debug = $state({
  startCount: 0,
  tickCount: 0,
  lastTickAt: '',
  lastView: '',
  lastError: '',
});

let polling = false;

export function startAgentPolling(): void {
  debug.startCount += 1;
  if (polling) return;
  polling = true;

  const tick = async () => {
    debug.tickCount += 1;
    debug.lastTickAt = new Date().toLocaleTimeString('et-EE');
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) {
        debug.lastError = `HTTP ${r.status}`;
        setTimeout(tick, 1000);
        return;
      }
      const data = (await r.json()) as AgentState;
      debug.lastView = data.view ?? 'no-view';
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
    } catch (e) {
      debug.lastError = String(e);
    }
    setTimeout(tick, 1000);
  };
  tick();
}
