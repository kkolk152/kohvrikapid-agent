#!/usr/bin/env bash
# Kohvrikapid Agent installer Raspberry Pi-le (Debian/Raspberry Pi OS).
# Käivita:
#   curl -fsSL https://github.com/kkolk152/kohvrikapid-agent/raw/main/install.sh | sudo bash
# või lokaalne kloon:
#   sudo ./install.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kkolk152/kohvrikapid-agent.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/kohvrikapid-agent}"
CONFIG_DIR="/etc/kohvrikapid-agent"
STATE_DIR="/var/lib/kohvrikapid-agent"
LOG_DIR="/var/log/kohvrikapid-agent"
SERVICE_USER="kohvrikapid"
SERVER_URL_DEFAULT="${SERVER_URL:-https://ctr-locker.kakuweb.ee}"

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Käivita rootina (sudo)." >&2
    exit 1
  fi
}

ensure_deps() {
  echo "[1/7] Paigaldan Debiani paketid"
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git ca-certificates curl \
    busybox dnsmasq nftables usb-modeswitch udev iproute2 iputils-ping
  # NB: NetworkManager/ModemManager/dhcpcd-d EI paigalda — me kasutame
  # busybox udhcpc-d + custom systemd unit-eid (vt scripts/network/).
  # Vt network-bootstrap.sh, mis nad keelab/maskib paigalduse ajal.
}

ensure_user() {
  if ! id "$SERVICE_USER" &>/dev/null; then
    echo "[2/7] Loon kasutaja $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  else
    echo "[2/7] Kasutaja $SERVICE_USER on juba olemas"
  fi
  usermod -aG dialout,gpio,video,netdev "$SERVICE_USER" || true
}

clone_or_update() {
  echo "[3/7] Tarkvara ${INSTALL_DIR}"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --quiet
    git -C "$INSTALL_DIR" reset --hard origin/main --quiet
  else
    rm -rf "$INSTALL_DIR"
    git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
}

install_venv() {
  echo "[4/7] Python venv + sõltuvused"
  if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
    python3 -m venv "$INSTALL_DIR/.venv"
  fi
  "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"
}

write_config() {
  echo "[5/7] Konfiguratsioon $CONFIG_DIR"
  mkdir -p "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
  chmod 750 "$CONFIG_DIR" "$STATE_DIR"
  if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
    cat > "$CONFIG_DIR/config.toml" <<EOF
# Kohvrikapid agent — konfiguratsioon
server_url = "$SERVER_URL_DEFAULT"
long_poll_timeout = 30
long_poll_retry_seconds = 5
firmware_install_command = "/opt/kohvrikapid-agent/bin/install-firmware.sh"
# display_mode: "auto" (vaatab /dev/fb0), "force_on", "force_off"
display_mode = "auto"
discovery_enabled = true
discovery_interval_minutes = 30
# serial_port = "/dev/ttyUSB0"   # ava kui RS485 dongl
# serial_baud = 19200
EOF
    chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR/config.toml"
    chmod 640 "$CONFIG_DIR/config.toml"
  fi
}

install_network_bootstrap() {
  echo "[6/7] Network bootstrap (udhcpc usb0/eth0 + dnsmasq + nft NAT)"
  # network-bootstrap.sh paigaldab kõik /usr/local/sbin skriptid,
  # systemd unit-id, dnsmasq drop-in ja keelab konkureerivad daemonid.
  INSTALL_DIR="$INSTALL_DIR" bash "$INSTALL_DIR/scripts/network-bootstrap.sh"
}

install_service() {
  echo "[7/7] systemd unit"
  install -m 644 "$INSTALL_DIR/systemd/kohvrikapid-agent.service" /etc/systemd/system/
  install -d -m 755 /opt/kohvrikapid-agent/bin
  install -m 755 "$INSTALL_DIR/scripts/install-firmware.sh" /opt/kohvrikapid-agent/bin/install-firmware.sh
  systemctl daemon-reload
  systemctl enable --now kohvrikapid-agent.service
  sleep 2
  systemctl status --no-pager kohvrikapid-agent.service || true
}

require_root
ensure_deps
ensure_user
clone_or_update
install_venv
write_config
install_network_bootstrap
install_service

cat <<EOF

✅ Kohvrikapid Agent paigaldatud.

Seerianumber: $(/opt/kohvrikapid-agent/.venv/bin/kohvrikapid-agent --serial)

Järgmised sammud:
  - Logi platformi (admin UI) sisse → /devices
  - Leia "Ootab sidumist" sektsioonist see seade
  - Vali platform + kapp ja kliki "Seo platformiga"

Kasulikud käsud:
  sudo systemctl status kohvrikapid-agent
  sudo journalctl -u kohvrikapid-agent -f
EOF
