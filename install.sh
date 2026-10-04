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
ENABLE_KIOSK="${ENABLE_KIOSK:-1}"   # 0 = ainult headless agent (ekraanita Pi)
UPDATE_MODE=0

# Olemasoleva toimiva installi uuendamisel ei tohi võrgu bootstrap'i uuesti
# käivitada: see peatab NetworkManageri/dhcpcd ja võib aktiivse SSH ühenduse
# katkestada. Poolikut esmapaigaldust ei loe me uuenduseks.
if [[ -d "$INSTALL_DIR/.git" \
   && -f "$CONFIG_DIR/config.toml" \
   && -f /etc/systemd/system/kohvrikapid-agent.service ]]; then
  UPDATE_MODE=1
fi

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Käivita rootina (sudo)." >&2
    exit 1
  fi
}

ensure_deps() {
  local base_packages=(
    python3 python3-venv python3-pip git ca-certificates curl
    busybox dnsmasq nftables usb-modeswitch udev iproute2 iputils-ping
    fonts-dejavu-core bluez
  )
  local kiosk_packages=(cage seatd cog nodejs npm)

  if [[ "$UPDATE_MODE" == "1" ]]; then
    local missing=()
    local pkg
    for pkg in "${base_packages[@]}"; do
      dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'ok installed' || missing+=("$pkg")
    done
    if [[ "$ENABLE_KIOSK" == "1" ]]; then
      for pkg in "${kiosk_packages[@]}"; do
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'ok installed' || missing+=("$pkg")
      done
    fi

    local need_chromium=0
    if [[ "$ENABLE_KIOSK" == "1" ]] \
      && ! command -v chromium >/dev/null 2>&1 \
      && ! command -v chromium-browser >/dev/null 2>&1; then
      need_chromium=1
    fi

    if [[ ${#missing[@]} -eq 0 && "$need_chromium" == "0" ]]; then
      echo "[1/9] Uuendusrežiim: süsteemipaketid on olemas, jätan apt-i vahele"
      return
    fi

    echo "[1/9] Uuendusrežiim: paigaldan ainult puuduvad paketid: ${missing[*]:-(chromium)}"
    apt-get update -qq
    if [[ "$need_chromium" == "1" ]]; then
      local chromium_pkg="chromium"
      if ! apt-cache show chromium &>/dev/null; then
        chromium_pkg="chromium-browser"
      fi
      missing+=("$chromium_pkg")
    fi
    apt-get install -y --no-install-recommends "${missing[@]}"
    return
  fi

  echo "[1/9] Paigaldan Debiani paketid"
  # Taasta katkenud dpkg/apt (nt kui image'i esmakaivitus / eelnev apt jai pooleli).
  # Ilma selleta failib apt-get: "dpkg was interrupted, run 'dpkg --configure -a'".
  dpkg --configure -a 2>/dev/null || true
  apt-get -f install -y 2>/dev/null || true
  apt-get update -qq
  apt-get install -y --no-install-recommends "${base_packages[@]}"

  if [[ "$ENABLE_KIOSK" == "1" ]]; then
    echo "[1b/9] Paigaldan kioski paketid (chromium + cage + node)"
    # Debian Trixie / uuem Pi OS -> chromium; Bookworm -> chromium-browser
    local chromium_pkg="chromium"
    if ! apt-cache show chromium &>/dev/null; then
      chromium_pkg="chromium-browser"
    fi
    apt-get install -y --no-install-recommends "$chromium_pkg" "${kiosk_packages[@]}"
  fi
}

ensure_user() {
  if ! id "$SERVICE_USER" &>/dev/null; then
    echo "[2/9] Loon kasutaja $SERVICE_USER"
    useradd --system --create-home --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
  else
    echo "[2/9] Kasutaja $SERVICE_USER on juba olemas"
  fi
  usermod -aG dialout,gpio,video,netdev,input,render,seat,tty,bluetooth "$SERVICE_USER" 2>/dev/null || \
    usermod -aG dialout,gpio,video,netdev,input,render,bluetooth "$SERVICE_USER" || true
}

clone_or_update() {
  echo "[3/9] Tarkvara ${INSTALL_DIR}"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --quiet
    git -C "$INSTALL_DIR" reset --hard origin/main --quiet
  else
    rm -rf "$INSTALL_DIR"
    git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
}

install_venv() {
  echo "[4/9] Python venv + sõltuvused"
  if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
    python3 -m venv "$INSTALL_DIR/.venv"
  fi
  "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
  "$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"
}

build_kiosk_ui() {
  if [[ "$ENABLE_KIOSK" != "1" ]]; then
    echo "[5/9] Kiosk UI build pole vajalik (ENABLE_KIOSK=0)"
    return
  fi
  echo "[5/9] Kioski UI build (Vite + Svelte)"
  cd "$INSTALL_DIR/kiosk"
  if [[ ! -d node_modules ]]; then
    npm ci --no-audit --no-fund --silent 2>&1 | tail -5
  fi
  if [[ ! -d dist ]] || [[ src/App.svelte -nt dist/index.html ]]; then
    npm run build 2>&1 | tail -5
  fi
  cd - >/dev/null
}

write_config() {
  echo "[6/9] Konfiguratsioon $CONFIG_DIR"
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
# Kui kiosk Chromium töötab, agent ei kasuta fb-d nagunii.
display_mode = "force_off"
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
  if [[ "$UPDATE_MODE" == "1" ]]; then
    echo "[7/9] Uuendusrežiim: värskendan võrgufailid ilma aktiivset võrku puutumata"
    NETWORK_BOOTSTRAP_REFRESH_ONLY=1 INSTALL_DIR="$INSTALL_DIR" \
      bash "$INSTALL_DIR/scripts/network-bootstrap.sh"
  else
    echo "[7/9] Network bootstrap (udhcpc usb0/eth0 + dnsmasq + nft NAT)"
    INSTALL_DIR="$INSTALL_DIR" bash "$INSTALL_DIR/scripts/network-bootstrap.sh"
  fi
}

apply_kernel_cmdline() {
  # Lisa fbcon=map:1 + consoleblank=0 (kioski jaoks fbcon ei tohi fb0-d hoida)
  local cmdline=/boot/firmware/cmdline.txt
  [[ -f $cmdline ]] || cmdline=/boot/cmdline.txt
  [[ -f $cmdline ]] || { echo "Hoiatus: cmdline.txt ei leitud"; return; }

  local need_reboot=0
  if ! grep -q "fbcon=map:1" "$cmdline"; then
    sed -i 's| *$| fbcon=map:1|' "$cmdline"
    need_reboot=1
  fi
  if ! grep -q "consoleblank=0" "$cmdline"; then
    sed -i 's| *$| consoleblank=0|' "$cmdline"
    need_reboot=1
  fi
  if [[ "$need_reboot" == "1" ]]; then
    echo "[8/9] Kerneli cmdline uuendatud (fbcon=map:1 consoleblank=0) — vajab REBOOT-i"
    NEED_REBOOT=1
  else
    echo "[8/9] Kerneli cmdline juba seadistatud"
  fi
}

install_service() {
  echo "[9/9] systemd unit-id"
  install -m 644 "$INSTALL_DIR/systemd/kohvrikapid-agent.service" /etc/systemd/system/
  install -d -m 755 /opt/kohvrikapid-agent/bin
  install -m 755 "$INSTALL_DIR/scripts/install-firmware.sh" /opt/kohvrikapid-agent/bin/install-firmware.sh
  install -m 755 "$INSTALL_DIR/scripts/update-rpi-connect.sh" /usr/local/sbin/kohvrikapid-update-rpi-connect
  install -m 644 "$INSTALL_DIR/systemd/kohvrikapid-rpi-connect-update.service" /etc/systemd/system/

  if [[ "$ENABLE_KIOSK" == "1" ]]; then
    install -m 644 "$INSTALL_DIR/systemd/kohvrikapid-kiosk.service" /etc/systemd/system/
  fi

  # Luba OTA self-update: baas-unit on range sandbox (ProtectSystem=strict,
  # ReadWritePaths ei kata /opt-i, NoNewPrivileges=true) -> agent EI SAA
  # install-firmware.sh-ga /opt-i uut firmware'i kirjutada ja OTA jaaks igavesse
  # loopi (jaaks vanale versioonile). Drop-in + sudoers annavad OTA-le kirjutuse.
  chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" 2>/dev/null || true
  install -d /etc/systemd/system/kohvrikapid-agent.service.d
  cat > /etc/systemd/system/kohvrikapid-agent.service.d/10-ota.conf <<'OTAEOF'
[Service]
# Neutraliseeri base-uniti sandbox TAIELIKULT. Ainult ReadWritePaths=/opt lisamisest
# EI PIISA: ProtectSystem=strict teeb /opt read-only mount-tasemel (ka sudo-root ei
# kirjuta) -> OTA tar kukub "Read-only file system". Tuhjad vaartused reset'ivad need
# direktiivid. Vastab firmware 0.2.90 non-sandboxed unitile; parast 1. edukat OTAt
# votab firmware oma unit yle.
ProtectSystem=false
ProtectHome=false
ReadOnlyPaths=
ReadWritePaths=
NoNewPrivileges=false
OTAEOF
  # Kitsas sudoers (mitte NOPASSWD:ALL): luba agendil ainult OTA-paigaldusskript
  # root-ina kaivitada. install-firmware.sh eskaleerub ise `sudo -n`-iga. Katab nii
  # bin/ kui scripts/ tee (config default = bin/). Uhtib firmware sudoers-failiga.
  cat > /etc/sudoers.d/kohvrikapid-ota <<SUDOEOF
$SERVICE_USER ALL=(root) NOPASSWD: /opt/kohvrikapid-agent/bin/install-firmware.sh
$SERVICE_USER ALL=(root) NOPASSWD: /opt/kohvrikapid-agent/scripts/install-firmware.sh
$SERVICE_USER ALL=(root) NOPASSWD: /opt/kohvrikapid-agent/scripts/enable-modem-at.sh
SUDOEOF
  chmod 440 /etc/sudoers.d/kohvrikapid-ota

  systemctl daemon-reload
  if [[ "$UPDATE_MODE" == "1" ]]; then
    systemctl enable kohvrikapid-agent.service
    systemctl restart kohvrikapid-agent.service
  else
    systemctl enable --now kohvrikapid-agent.service
  fi
  if [[ "$ENABLE_KIOSK" == "1" ]]; then
    if [[ "$UPDATE_MODE" == "1" ]]; then
      systemctl enable kohvrikapid-kiosk.service || true
      systemctl try-restart kohvrikapid-kiosk.service || true
    else
      systemctl enable --now kohvrikapid-kiosk.service || true
    fi
  fi
  sleep 2
  systemctl status --no-pager kohvrikapid-agent.service || true
}

NEED_REBOOT=0

require_root

# --- tmux: hoia install elus ka kui SSH katkeb (vorgu umberseadistus katkestab eth0-SSH-i) ---
# Kui me pole juba tmux-is, paigalda tmux, lae skript ja kaivita see tmux-sessioonis "kohv".
if [[ -z "${TMUX:-}" && "${KOHV_IN_TMUX:-}" != "1" ]]; then
  if ! command -v tmux >/dev/null 2>&1; then
    dpkg --configure -a 2>/dev/null || true
    apt-get update -qq 2>/dev/null || true
    apt-get install -y --no-install-recommends tmux 2>/dev/null || true
  fi
  if command -v tmux >/dev/null 2>&1; then
    SELF=/tmp/kohvrikapid-install.sh
    if curl -fsSL "https://github.com/kkolk152/kohvrikapid-agent/raw/main/install.sh" -o "$SELF" 2>/dev/null && [[ -s "$SELF" ]]; then
      chmod +x "$SELF"
      echo "===================================================================="
      echo " Kaivitan installi tmux-sessioonis 'kohv' (SSH voib katkeda — see on OK)."
      echo "   Taasuhendu + jatka:   sudo tmux attach -t kohv"
      echo "   Voi jalgi logi:       sudo tail -f /var/log/kohv-install.log"
      echo "===================================================================="
      sleep 2
      tmux kill-session -t kohv 2>/dev/null || true
      tmux new-session -d -s kohv "KOHV_IN_TMUX=1 ENABLE_KIOSK='${ENABLE_KIOSK}' SERVER_URL='${SERVER_URL_DEFAULT}' bash '$SELF' 2>&1 | tee /var/log/kohv-install.log; echo; echo '=== INSTALL LOPETATUD — vajuta Enter et aken sulgeda ==='; read -r"
      echo "tmux sessioon 'kohv' kaivitatud taustal.  Jalgimiseks:  sudo tmux attach -t kohv"
      exit 0
    fi
  fi
  echo "HOIATUS: tmux pole saadaval — jooksen otse. SSH katkemisel install katkeb." >&2
fi

ensure_deps
ensure_user
clone_or_update
install_venv
build_kiosk_ui
write_config
install_network_bootstrap
if [[ "$UPDATE_MODE" == "1" ]]; then
  echo "[8/9] Uuendusrežiim: kerneli ja võrgu algseadistust ei muudeta"
else
  apply_kernel_cmdline
fi
install_service

touch "$STATE_DIR/.install-complete"

cat <<EOF

✅ Kohvrikapid Agent $([[ "$UPDATE_MODE" == "1" ]] && echo "uuendatud" || echo "paigaldatud").

Seerianumber: $(/opt/kohvrikapid-agent/.venv/bin/kohvrikapid-agent --serial)

Järgmised sammud:
  - Logi platformi (admin UI) sisse → /devices
  - Leia "Ootab sidumist" sektsioonist see seade
  - Vali platform + kapp ja kliki "Seo platformiga"

Kasulikud käsud:
  sudo systemctl status kohvrikapid-agent kohvrikapid-kiosk
  sudo journalctl -u kohvrikapid-agent -f
  sudo journalctl -u kohvrikapid-kiosk -f
  sudo systemctl start --no-block kohvrikapid-rpi-connect-update
  sudo journalctl -u kohvrikapid-rpi-connect-update -f
EOF

if [[ "$NEED_REBOOT" == "1" ]]; then
  cat <<EOF

⚠ Kerneli cmdline muudeti (fbcon=map:1 consoleblank=0).
   Käivita sudo reboot, et kioski ekraan korralikult tööle saada.
EOF
fi
