export type AgentState = {
  view: 'BOOTING' | 'UNCLAIMED' | 'READY' | 'ERROR';
  title?: string;
  message?: string;
  lines?: string[];
  cabinet_name?: string;
  cabinet_kind?: 'vending' | 'rental' | 'storage' | 'parcel' | 'charging' | string;
  slot_status?: Record<string, unknown>;
  slot_count?: number;
  slot_sizes?: string[];
  // Bränd / tenant (long-pollist)
  tenant_name?: string;
  contact_phone?: string;
  contact_email?: string;
  logo_data_uri?: string;
  logo_url?: string;
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

export type StorageStartResponse = {
  ok: boolean;
  session_id?: string;
  slot_code?: string;
  pin?: string;
  expires_at?: string;
  open_command_id?: string;
  error?: string;
};

export type StorageVerifyResponse = {
  ok: boolean;
  session_id?: string;
  slot_code?: string;
  command_id?: string;
  expires_at?: string;
  error?: string;
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

export async function verifyStoragePin(pin: string): Promise<StorageVerifyResponse> {
  const r = await fetch('/api/storage/verify-pin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  });
  return (await r.json()) as StorageVerifyResponse;
}

export async function startStorage(payload: {
  customer_phone?: string;
  minutes?: number;
  slot_code?: string;
}): Promise<StorageStartResponse> {
  const r = await fetch('/api/storage/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return (await r.json()) as StorageStartResponse;
}

/** Kappide loend state-ist: arv (slot_count) + suurused (slot_sizes) + hõivatus (slot_status). */
export type SlotInfo = { code: string; number: string; size: string; occupied: boolean };

export function buildSlots(state: AgentState): SlotInfo[] {
  const n = Math.max(0, Number(state.slot_count ?? 0));
  const sizes = state.slot_sizes ?? [];
  const status = (state.slot_status ?? {}) as Record<string, unknown>;
  const out: SlotInfo[] = [];
  for (let i = 1; i <= n; i++) {
    const code = String(i);
    const raw = status[code] ?? status[String(i).padStart(2, '0')];
    const occupied =
      raw === 'occupied' ||
      raw === true ||
      (typeof raw === 'object' && raw !== null && (raw as { occupied?: boolean }).occupied === true);
    out.push({
      code,
      number: String(i).padStart(2, '0'),
      size: (sizes[i - 1] || 'M').toUpperCase(),
      occupied,
    });
  }
  return out;
}
