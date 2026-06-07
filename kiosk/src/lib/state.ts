export type AgentState = {
  view: 'BOOTING' | 'UNCLAIMED' | 'READY' | 'ERROR';
  title?: string;
  message?: string;
  lines?: string[];
  qr_url?: string;
  qr_label?: string;
  cabinet_name?: string;
  cabinet_kind?: string;
  slot_status?: Record<string, unknown>;
  network?: {
    mode?: string;
    hat_present?: boolean;
    eth0_ip?: string;
    usb0_ip?: string;
    discovery_subnet?: string;
    cellular_signal_percent?: number;
  };
  agent_version?: string;
  firmware_version?: string;
  serial?: string;
  last_seen_at?: string;
};

const POLL_INTERVAL_MS = 1000;

export function startStateStream(onState: (state: AgentState) => void): () => void {
  let cancelled = false;
  let timer: number | null = null;

  async function tick() {
    if (cancelled) return;
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (r.ok) {
        const data = (await r.json()) as AgentState;
        onState(data);
      }
    } catch {
      // network blip — try again next tick
    }
    if (!cancelled) timer = window.setTimeout(tick, POLL_INTERVAL_MS);
  }

  tick();

  return () => {
    cancelled = true;
    if (timer) window.clearTimeout(timer);
  };
}
