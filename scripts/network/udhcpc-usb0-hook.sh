#!/bin/sh
# busybox udhcpc hook usb0 jaoks (4G primary).
# Paigaldatakse: /usr/local/sbin/udhcpc-usb0-hook.sh
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

    # 4G primary default route
    while ip -4 route del default dev "$iface" 2>/dev/null; do :; done
    [ -n "${router:-}" ] && ip -4 route add default via "$router" dev "$iface" metric 50 || true

    printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" > /etc/resolv.conf
    ;;
esac
