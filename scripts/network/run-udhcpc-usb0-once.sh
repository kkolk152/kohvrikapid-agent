#!/usr/bin/env bash
# udhcpc one-shot usb0 jaoks (4G HAT modem ECM/RNDIS liides).
# Paigaldatakse: /usr/local/sbin/run-udhcpc-usb0-once.sh
set -euo pipefail

[ -e /sys/class/net/usb0 ] || exit 0

# Kui usb0 juba on ja TCP toimib, ära torgi
if ip -4 addr show dev usb0 | grep -q "inet " ; then
  timeout 2 bash -c 'cat </dev/null >/dev/tcp/1.1.1.1/443' >/dev/null 2>&1 && exit 0
fi

ip link set usb0 up || true
/bin/busybox udhcpc -q -n -i usb0 -p /run/udhcpc.usb0.pid \
  -s /usr/local/sbin/udhcpc-usb0-hook.sh -T 3 -t 5
