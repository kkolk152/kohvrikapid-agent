#!/usr/bin/env bash
# udhcpc one-shot eth0 jaoks (LAN klient režiim).
# Paigaldatakse: /usr/local/sbin/run-udhcpc-eth0-once.sh
set -euo pipefail

ip link set eth0 up || true

# Kui eth0 juba on ja gateway vastab, ära torgi (väldib SSH droppe)
gw="$(ip -4 route show default dev eth0 | awk '/default/ {print $3; exit}')"
if ip -4 addr show dev eth0 | grep -q "inet " && [ -n "$gw" ]; then
  ping -I eth0 -c1 -W1 "$gw" >/dev/null 2>&1 && exit 0
fi

/bin/busybox udhcpc -q -n -i eth0 -p /run/udhcpc.eth0.pid \
  -s /usr/local/sbin/udhcpc-eth0-hook.sh -T 3 -t 5
