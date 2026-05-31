# Kohvrikapid Agent

Raspberry Pi (ja teiste väikearvutite) agent, mis ühendab füüsilise kohvrikapi
[Kohvrikapid](https://github.com/kkolk152/kohvrikapid-platform) SaaS-platformiga.

## Disain — turvaline outbound-only ühendus

Pi **ei ava** ühtegi sissetulevat porti. Kogu suhtlus serveriga toimub agendi
poolt algatatud HTTPS-päringutega:

1. **Esmaregistratsioon** — esmakäivitusel saadab Pi serverile oma seerianumbri,
   saab tagasi `device_id` + `agent_token` (token salvestatakse `/etc/kohvrikapid-agent/secrets.toml`,
   ainult `root` saab lugeda).
2. **Long-poll** — kogu suhtlus pärast registratsiooni käib läbi `POST /api/agent/v1/long-poll`,
   mis blokeerub serveris kuni 25 sekundit. Kohe kui server saab käsku (avada pesa,
   sünkroniseerida laoseis, paigaldada uus firmware), saadab vastuse — agent
   ackib seda samal kanalil.
3. **OTA** — kui server tagastab `firmware_pending`, laadib agent uue binaari
   alla, kontrollib SHA-256 ja paigaldab `systemd-run` abil. Pärast paigaldust
   `POST /api/agent/v1/firmware/{id}/applied`.

Kõik need on `Authorization: Bearer <agent_token>` + `X-Device-Id: <uuid>` päised.
Server salvestab ainult `sha256(agent_token)` — kui Pi varastatakse, saab admin
UI-st seadme "revoke" — agent kaotab koheselt ligipääsu.

## Esmakordne käivitamine kapis

Pi käivitudes ilma claim-iga:

```
┌─────────────────────────────────────────┐
│                                         │
│   KOHVRIKAPID                           │
│                                         │
│   Ootan administraatori sidumist…       │
│                                         │
│   Seerianumber:  PI-A1B2-C3D4           │
│   Tarkvara:      agent 0.1.0 / fw 1.0.0 │
│   Võrk:          10.10.10.42 (wlan0)    │
│                                         │
│   ┌────────┐                            │
│   │ QR-kood│  → kohvrikapid.ee/claim/   │
│   └────────┘    PI-A1B2-C3D4            │
│                                         │
└─────────────────────────────────────────┘
```

Admin skannib QR-koodi (või sisestab seerianumbri UI-s `/devices`) ja seob
seadme platformiga + kapiga. Agent saab järgmise long-pollil-i jooksul (≤25s)
kogu kapi konfiguratsiooni (kapi tüüp, lukukontrolleri seaded, pesade list).

## Paigaldus

```bash
curl -fsSL https://github.com/kkolk152/kohvrikapid-agent/raw/main/install.sh | sudo bash
```

Skript:
- loob kasutaja `kohvrikapid` (no-login),
- paigaldab `/opt/kohvrikapid-agent/` virtualenv-i ja Python-paketi,
- kirjutab `/etc/kohvrikapid-agent/config.toml` (server URL),
- registreerib `systemd` unit-i `kohvrikapid-agent.service`,
- käivitab ja näitab esmakordse käivituse ekraani.

## Käsureal

```bash
sudo systemctl status kohvrikapid-agent
sudo journalctl -u kohvrikapid-agent -f
kohvrikapid-agent --serial      # Näita seerianumbrit
kohvrikapid-agent --reset       # Kustuta secrets + sunni uus registratsioon
```

## Arendus

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pytest
```

## Litsents

Apache 2.0 — vt LICENSE.
