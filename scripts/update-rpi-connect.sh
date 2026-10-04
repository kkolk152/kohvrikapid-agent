#!/usr/bin/env bash
# Uuenda Raspberry Pi Connect süsteemse taustatööna.
#
# Connecti paketi uuendus katkestab aktiivse Remote Desktopi / remote shelli.
# Seda skripti käivitab systemd system-service, mistõttu apt/dpkg jätkab tööd ka
# pärast Connecti kasutajaseansi sulgumist. Lõpus käivitatakse Connect uuesti.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

STATE_DIR=/var/lib/kohvrikapid-agent
STATUS_FILE="$STATE_DIR/rpi-connect-update.status"
LOCK_FILE=/run/lock/kohvrikapid-rpi-connect-update.lock
CONNECT_USER="${RPI_CONNECT_USER:-}"

mkdir -p "$STATE_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Raspberry Pi Connecti uuendus juba töötab."
  exit 0
fi

write_status() {
  printf 'status=%s\nts=%s\nmessage=%s\n' "$1" "$(date -u +%FT%TZ)" "$2" > "$STATUS_FILE"
}

failed() {
  local rc=$?
  write_status failed "Uuendus ebaõnnestus (exit=$rc). Vaata journalctl -u kohvrikapid-rpi-connect-update."
  exit "$rc"
}
trap failed ERR

if dpkg-query -W -f='${Status}' rpi-connect 2>/dev/null | grep -q 'ok installed'; then
  CONNECT_PACKAGE=rpi-connect
elif dpkg-query -W -f='${Status}' rpi-connect-lite 2>/dev/null | grep -q 'ok installed'; then
  CONNECT_PACKAGE=rpi-connect-lite
else
  write_status failed "rpi-connect ega rpi-connect-lite ei ole paigaldatud."
  echo "Raspberry Pi Connect ei ole paigaldatud." >&2
  exit 2
fi

if [[ -z "$CONNECT_USER" ]]; then
  # Eelista kasutajat, kelle kodus on Connecti seadistus. Kui seda ei leia,
  # vali esimene tavaline (UID >= 1000) kasutaja.
  for home_dir in /home/*; do
    [[ -d "$home_dir/.config/com.raspberrypi.connect" ]] || continue
    CONNECT_USER=$(basename "$home_dir")
    break
  done
fi
if [[ -z "$CONNECT_USER" ]]; then
  CONNECT_USER=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 { print $1; exit }')
fi

write_status running "Uuendan paketti $CONNECT_PACKAGE. Remote Desktop võib ajutiselt katkeda."
echo "Uuendan Raspberry Pi Connecti paketti: $CONNECT_PACKAGE"
apt-get -o DPkg::Lock::Timeout=600 update -qq
apt-get -o DPkg::Lock::Timeout=600 install -y --only-upgrade "$CONNECT_PACKAGE"

if [[ -n "$CONNECT_USER" ]] && id "$CONNECT_USER" >/dev/null 2>&1; then
  CONNECT_UID=$(id -u "$CONNECT_USER")
  loginctl enable-linger "$CONNECT_USER" 2>/dev/null || true
  systemctl start "user@${CONNECT_UID}.service" 2>/dev/null || true
  sleep 2

  CONNECT_ENV=(
    "XDG_RUNTIME_DIR=/run/user/$CONNECT_UID"
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$CONNECT_UID/bus"
  )
  runuser -u "$CONNECT_USER" -- env "${CONNECT_ENV[@]}" rpi-connect on 2>/dev/null || true
  runuser -u "$CONNECT_USER" -- env "${CONNECT_ENV[@]}" rpi-connect restart 2>/dev/null || true
  echo "Connecti kasutajateenus taastatud kasutajale: $CONNECT_USER"
else
  echo "Hoiatus: Connecti kasutajat ei leitud; pakett uuendati, kuid kasutajateenust ei taaskäivitatud." >&2
fi

write_status success "Pakett $CONNECT_PACKAGE on uuendatud; Connecti teenus käivitati uuesti."
echo "Raspberry Pi Connecti uuendus lõpetatud."

