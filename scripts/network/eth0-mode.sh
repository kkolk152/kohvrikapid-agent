#!/usr/bin/env bash
# Lülita eth0 LAN-kliendi ja router-režiimi vahel.
#
# Loogika:
#   - eth0 carrier=0 (kaabel sees pole)  → router-mode (kui usb0 olemas, jagame)
#   - eth0 carrier=1 + DHCP server vastab → LAN-client mode
#   - eth0 carrier=1 + DHCP ei vasta      → router-mode
#
# Paigaldatakse: /usr/local/sbin/eth0-mode.sh
set -euo pipefail

LANIF=eth0
WANIF=usb0

LAN_IP=192.168.100.1/24
USB_GW=192.168.200.1

carrier() { cat "/sys/class/net/$LANIF/carrier" 2>/dev/null || echo 0; }

flush_nat() {
  nft delete table ip kohvrikapid_nat 2>/dev/null || true
}

dhcp_offer_exists() {
  # -n: exit !=0 kui ei saa lease
  # -s /bin/true: ainult proobimine, ära konfi
  /bin/busybox udhcpc -n -q -i "$LANIF" -t 1 -T 2 -s /bin/true >/dev/null 2>&1
}

router_mode() {
  logger -t eth0-mode "ROUTER mode (eth0=$LAN_IP, DHCP+NAT ON)"
  systemctl stop udhcpc-eth0.timer 2>/dev/null || true

  ip link set "$LANIF" up || true
  ip -4 addr flush dev "$LANIF" || true
  ip addr add "$LAN_IP" dev "$LANIF" 2>/dev/null || true

  sysctl -w net.ipv4.ip_forward=1 >/dev/null

  flush_nat
  nft add table ip kohvrikapid_nat 2>/dev/null || true
  nft 'add chain ip kohvrikapid_nat postrouting { type nat hook postrouting priority srcnat; policy accept; }' 2>/dev/null || true
  nft 'add chain ip kohvrikapid_nat forward { type filter hook forward priority filter; policy drop; }' 2>/dev/null || true
  nft add rule ip kohvrikapid_nat forward ct state established,related accept 2>/dev/null || true
  nft add rule ip kohvrikapid_nat forward iifname "$LANIF" oifname "$WANIF" accept 2>/dev/null || true
  nft add rule ip kohvrikapid_nat postrouting ip saddr 192.168.100.0/24 oifname "$WANIF" masquerade 2>/dev/null || true

  systemctl restart dnsmasq.service

  # Garanteeri 4G default route
  while ip -4 route del default dev "$WANIF" 2>/dev/null; do :; done
  ip -4 route add default via "$USB_GW" dev "$WANIF" metric 50 || true
}

lan_client_mode() {
  logger -t eth0-mode "LAN-CLIENT mode (DHCP server OFF, eth0=DHCP client)"
  systemctl stop dnsmasq.service 2>/dev/null || true
  flush_nat
  sysctl -w net.ipv4.ip_forward=0 >/dev/null || true

  systemctl start udhcpc-eth0.service 2>/dev/null || true
  systemctl start udhcpc-eth0.timer 2>/dev/null || true
}

# MAIN
if [ "$(carrier)" != "1" ]; then
  router_mode
  exit 0
fi

if dhcp_offer_exists; then
  lan_client_mode
else
  router_mode
fi
