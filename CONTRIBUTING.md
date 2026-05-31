# Contributing

## Kohalik arendus

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
ruff check .
pytest -q
```

Agent käitub macOS-il ja Linux-il (Pi puhul kasutusvalmis). Konfiguratsiooni
saab määrata keskkonnamuutujatega:

```bash
export KOHVRIKAPID_CONFIG=$PWD/dev-config.toml
export KOHVRIKAPID_SECRETS=$PWD/dev-secrets.toml
kohvrikapid-agent --run
```

`dev-config.toml`:

```toml
server_url = "http://192.168.15.244:8090"
display_enabled = false
```

## Branch / commit konventsioon

- `main` — production-ready
- `feat/*`, `fix/*`, `chore/*` — feature branchid, mergetakse PR-iga
- Commit-messaged inglise keeles, käskiv vorm ("Add X", "Fix Y")

## OTA paigaldamise testimine

1. Kohalikus arenduses lisa platformi UI-st (`/firmware`) uus tar.gz versioon (sisaldav `kohvrikapid_agent/` kaust).
2. Saada uuendus seadmele (`/devices/{id}` → "Saada uuendus").
3. Agent peaks järgmise long-polli ajal alla laadima, kontrollima sha256-d ja kutsuma `install-firmware.sh`-i.
