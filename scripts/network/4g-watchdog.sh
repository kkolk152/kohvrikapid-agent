#!/usr/bin/env bash
# Perioodiline watchdog 4G ühenduse jaoks. Kui usb0 IP olemas aga TCP ei tööta
# THRESH järjest, peatab + tõstab uuesti usb0 + uuendab DHCP-d.
# Paigaldatakse: /usr/local/sbin/4g-watchdog.sh
set -euo pipefail

USBIF=usb0
USB_GW=192.168.200.1

FAILFILE=/run/4g-watchdog.fail
TSFILE=/run/4g-watchdog.ts

COOLDOWN=180   # sek
THRESH=4       # mitu järjest FAIL enne resetti

have_usb() { [ -e "/sys/class/net/$USBIF" ]; }
have_ip()  { ip -4 addr show dev "$USBIF" | grep -q "inet "; }

tcp_ok() {
  timeout 2 bash -c 'cat </dev/null >/dev/tcp/1.1.1.1/443' >/dev/null 2>&1 && return 0
  timeout 2 bash -c 'cat </dev/null >/dev/tcp/8.8.8.8/443' >/dev/null 2>&1 && return 0
  return 1
}

gw_ok() { ping -c1 -W1 "$USB_GW" >/dev/null 2>&1; }

fail_get() { [ -f "$FAILFILE" ] && cat "$FAILFILE" 2>/dev/null || echo 0; }
fail_set() { echo "$1" > "$FAILFILE"; }
fail_inc() { n="$(fail_get)"; n=$((n+1)); fail_set "$n"; echo "$n"; }
fail_reset() { rm -f "$FAILFILE"; }

cooldown_ok() {
  [ -f "$TSFILE" ] || return 0
  last="$(cat "$TSFILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  [ $((now-last)) -ge "$COOLDOWN" ]
}
mark_reset() { date +%s > "$TSFILE"; }

have_usb || exit 0
have_ip  || exit 0

if tcp_ok; then
  fail_reset
  exit 0
fi

n="$(fail_inc)"

if ! gw_ok; then
  logger -t 4g-watchdog "TCP fail (count=$n), gw NOT OK"
  exit 0
fi

logger -t 4g-watchdog "TCP fail (count=$n), gw OK"

[ "$n" -ge "$THRESH" ] || exit 0
cooldown_ok || { logger -t 4g-watchdog "Skip reset (cooldown)"; exit 0; }

logger -t 4g-watchdog "Resetting usb0 link..."
ip link set "$USBIF" down || true
sleep 2
ip link set "$USBIF" up || true

systemctl start udhcpc-usb0.service || true

while ip -4 route del default dev "$USBIF" 2>/dev/null; do :; done
ip -4 route add default via "$USB_GW" dev "$USBIF" metric 50 || true

mark_reset
fail_reset
