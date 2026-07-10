#!/usr/bin/env bash
# Skript, mida agent kutsub OTA paigalduseks.  $1 = paigaldatav fail.
#
# NB: OTA (ota.py) laeb faili alati .bin-suffiksiga tmp-faili, seega tuvastame
# tüübi SISU (magic-baitide) järgi, mitte laiendi järgi.
#
# tar.gz bundle = repo puu (src/, scripts/, systemd/, pyproject.toml ...) mis
# ekstrakteeritakse /opt/kohvrikapid-agent alla. Peale failivahetust teeme:
#   - venv paketi reinstall  (uus kood + uued sõltuvused, nt bleak solar jaoks)
#   - bluez olemasolu tagamine (BLE)
#   - systemd unit refresh + daemon-reload
#   - selle skripti enda uuendamine bin/ alla (järgmiste OTA-de jaoks)

set -euo pipefail
FILE="$1"
INSTALL_DIR="/opt/kohvrikapid-agent"
if [[ ! -f "$FILE" ]]; then
  echo "Faili pole: $FILE" >&2
  exit 1
fi

magic2=$(head -c2 "$FILE" | od -An -tx1 | tr -d ' \n' || true)
head8=$(head -c8 "$FILE" 2>/dev/null || true)

refresh_python_and_units() {
  if [[ -f "$INSTALL_DIR/scripts/install-firmware.sh" ]]; then
    install -m 755 "$INSTALL_DIR/scripts/install-firmware.sh" "$INSTALL_DIR/bin/install-firmware.sh" 2>/dev/null || true
  fi
  if [[ -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
    "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade "$INSTALL_DIR" || \
      echo "HOIATUS: pip install ebaõnnestus (kontrolli internetti)" >&2
  fi
  if ! command -v bluetoothd >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends bluez 2>/dev/null || true
  fi
  if [[ -f "$INSTALL_DIR/systemd/kohvrikapid-agent.service" ]]; then
    install -m 644 "$INSTALL_DIR/systemd/kohvrikapid-agent.service" /etc/systemd/system/ 2>/dev/null || true
  fi
  systemctl daemon-reload 2>/dev/null || true
}

if [[ "$magic2" == "1f8b" ]] || [[ "$FILE" == *.tar.gz || "$FILE" == *.tgz ]]; then
  # gzip → tar.gz bundle
  tar -xzf "$FILE" -C "$INSTALL_DIR" --strip-components=0
  refresh_python_and_units
  systemctl restart kohvrikapid-agent.service
elif [[ "$head8" == '!<arch>'* ]] || [[ "$FILE" == *.deb ]]; then
  # Debiani pakett
  dpkg -i "$FILE" || apt-get -f install -y
  systemctl restart kohvrikapid-agent.service
else
  echo "Tundmatu firmware fail (magic=$magic2) — paigalda käsitsi" >&2
  exit 2
fi
