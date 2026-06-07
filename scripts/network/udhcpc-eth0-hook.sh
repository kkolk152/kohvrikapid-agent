#!/bin/sh
# busybox udhcpc hook eth0 jaoks (LAN klient / fallback).
# Paigaldatakse: /usr/local/sbin/udhcpc-eth0-hook.sh
set -eu
iface="$interface"

pfx="$(python3 - <<'P'
import os
m=os.environ.get("subnet","255.255.255.0")
print(sum(bin(int(x)).count("1") for x in m.split(".")))
P
)"

case "$1" in
  deconfig)
    # ära puutu midagi - väldib katkestusi
    ;;
  bound|renew)
    if ! ip -4 addr show dev "$iface" | grep -q "inet $ip/"; then
      ip -4 addr flush dev "$iface" || true
      ip -4 addr add "$ip/$pfx" dev "$iface"
    fi

    # LAN default route (kõrgem metric kui usb0 — kasutame seda ainult kui usb0 puudub)
    while ip -4 route del default dev "$iface" 2>/dev/null; do :; done
    [ -n "${router:-}" ] && ip -4 route add default via "$router" dev "$iface" metric 300 || true
    ;;
esac
