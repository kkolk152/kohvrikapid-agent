#!/usr/bin/env bash
# Kohvrikapid network bootstrap — paigaldab kõik udhcpc/dnsmasq/nft skriptid
# süsteemi (/usr/local/sbin, /etc/dnsmasq.d, /etc/systemd/system) ja keelab
# konkureerivad daemon-id (NetworkManager, dhcpcd, ModemManager).
#
# Käivitatakse install.sh-st AINULT ühe korra paigalduse ajal. Pärast seda
# haldavad ise paigaldatud systemd unit-id (udhcpc-usb0, udhcpc-eth0,
# eth0-mode, 4g-watchdog) tegeliku võrgu seisu.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/kohvrikapid-agent}"
SRC_NET_DIR="$INSTALL_DIR/scripts/network"
SRC_UNIT_DIR="$INSTALL_DIR/systemd/network"
SRC_CONFIG_DIR="$INSTALL_DIR/config"

log() { logger -t kohvrikapid-net-bootstrap -- "$*"; echo "[net-bootstrap] $*"; }

[[ $EUID -eq 0 ]] || { echo "Käivita rootina"; exit 1; }

log "Keelan konkureerivad võrgu daemon-id"
systemctl disable --now dhcpcd 2>/dev/null || true
systemctl disable --now NetworkManager 2>/dev/null || true
systemctl disable --now ModemManager 2>/dev/null || true
systemctl mask ModemManager 2>/dev/null || true
# dnsmasq käivitatakse ainult router-režiimis (eth0-mode.sh)
systemctl disable dnsmasq 2>/dev/null || true

log "Paigaldan skriptid /usr/local/sbin"
install -d -m 755 /usr/local/sbin
install -m 755 "$SRC_NET_DIR/run-udhcpc-usb0-once.sh"  /usr/local/sbin/run-udhcpc-usb0-once.sh
install -m 755 "$SRC_NET_DIR/run-udhcpc-eth0-once.sh"  /usr/local/sbin/run-udhcpc-eth0-once.sh
install -m 755 "$SRC_NET_DIR/udhcpc-usb0-hook.sh"      /usr/local/sbin/udhcpc-usb0-hook.sh
install -m 755 "$SRC_NET_DIR/udhcpc-eth0-hook.sh"      /usr/local/sbin/udhcpc-eth0-hook.sh
install -m 755 "$SRC_NET_DIR/eth0-mode.sh"             /usr/local/sbin/eth0-mode.sh
install -m 755 "$SRC_NET_DIR/4g-watchdog.sh"           /usr/local/sbin/4g-watchdog.sh
install -m 755 "$SRC_NET_DIR/calyx-up.sh"              /usr/local/sbin/calyx-up.sh

log "Paigaldan systemd unit-id"
install -m 644 "$SRC_UNIT_DIR/udhcpc-usb0.service"  /etc/systemd/system/udhcpc-usb0.service
install -m 644 "$SRC_UNIT_DIR/udhcpc-usb0.timer"    /etc/systemd/system/udhcpc-usb0.timer
install -m 644 "$SRC_UNIT_DIR/udhcpc-eth0.service"  /etc/systemd/system/udhcpc-eth0.service
install -m 644 "$SRC_UNIT_DIR/udhcpc-eth0.timer"    /etc/systemd/system/udhcpc-eth0.timer
install -m 644 "$SRC_UNIT_DIR/eth0-mode.service"    /etc/systemd/system/eth0-mode.service
install -m 644 "$SRC_UNIT_DIR/eth0-mode.timer"      /etc/systemd/system/eth0-mode.timer
install -m 644 "$SRC_UNIT_DIR/eth0-mode.path"       /etc/systemd/system/eth0-mode.path
install -m 644 "$SRC_UNIT_DIR/4g-watchdog.service"  /etc/systemd/system/4g-watchdog.service
install -m 644 "$SRC_UNIT_DIR/4g-watchdog.timer"    /etc/systemd/system/4g-watchdog.timer
install -m 644 "$SRC_UNIT_DIR/calyx-up.service"     /etc/systemd/system/calyx-up.service

log "Paigaldan dnsmasq drop-in"
install -d -m 755 /etc/dnsmasq.d
install -m 644 "$SRC_CONFIG_DIR/dnsmasq-kohvrikapid-lan.conf" /etc/dnsmasq.d/kohvrikapid-lan.conf

log "Lülitan IP-forward (sysctl drop-in)"
install -d -m 755 /etc/sysctl.d
cat > /etc/sysctl.d/99-kohvrikapid-ipforward.conf <<EOF
# Kohvrikapid — eth0 → usb0 NAT-i jaoks
net.ipv4.ip_forward=1
EOF
sysctl -p /etc/sysctl.d/99-kohvrikapid-ipforward.conf >/dev/null || true

log "Aktiveerin systemd timer-id ja path-i"
systemctl daemon-reload
systemctl enable --now udhcpc-usb0.timer
systemctl enable --now udhcpc-eth0.timer
systemctl enable --now eth0-mode.timer
systemctl enable --now eth0-mode.path
systemctl enable --now 4g-watchdog.timer
systemctl enable calyx-up.service || true

# Esimene käivitus kohe
systemctl start calyx-up.service || true
systemctl start udhcpc-usb0.service || true
systemctl start eth0-mode.service || true

log "Network bootstrap valmis."
