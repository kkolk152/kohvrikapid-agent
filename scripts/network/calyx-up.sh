#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin

VID="1d12"
PID="0101"

log(){ logger -t calyx-up "$*"; echo "[calyx-up] $*"; }

# lock to avoid overlaps
exec 9>/run/calyx-up.lock
flock -n 9 || exit 0

usb0_ok() {
  ip link show usb0 >/dev/null 2>&1 || return 1
  ip -4 addr show dev usb0 | grep -q 'inet ' || return 1
  curl -4 --interface usb0 -k -m 4 -sS https://1.1.1.1/ -o /dev/null
}

if usb0_ok; then
  log "usb0 OK -> no action"
  exit 0
fi

modprobe rndis_host 2>/dev/null || true
modprobe cdc_ether 2>/dev/null || true
modprobe option 2>/dev/null || true

find_base() {
  for d in /sys/bus/usb/devices/*; do
    [ -f "$d/idVendor" ] || continue
    v="$(cat "$d/idVendor")"; p="$(cat "$d/idProduct")"
    b="$(basename "$d")"
    if [ "$v" = "$VID" ] && [ "$p" = "$PID" ] && [[ "$b" != *:* ]]; then
      echo "$b"; return 0
    fi
  done
  return 1
}

BASE="$(find_base || true)"
[ -n "$BASE" ] || { log "device $VID:$PID not found"; exit 0; }
log "base=$BASE"

IF0="$BASE:1.0"
IF1="$BASE:1.1"

driver_of() {
  local IF="$1"
  if [ -L "/sys/bus/usb/devices/$IF/driver" ]; then
    basename "$(readlink -f "/sys/bus/usb/devices/$IF/driver")"
  else
    echo "none"
  fi
}

unbind_any() {
  local IF="$1"
  local d
  d="$(driver_of "$IF")"
  if [ "$d" != "none" ] && [ "$d" != "rndis_host" ]; then
    log "$IF bound to $d -> unbind"
    echo -n "$IF" > "/sys/bus/usb/drivers/$d/unbind" 2>/dev/null || true
  fi
}

bind_rndis_once() {
  local IF="$1"
  echo -n "$IF" > /sys/bus/usb/drivers/rndis_host/bind 2>/dev/null || true
}

# --- critical: UNBIND BOTH FIRST ---
unbind_any "$IF0"
unbind_any "$IF1"
sleep 0.5

# then bind both to rndis_host (retry a bit)
for _ in $(seq 1 80); do
  bind_rndis_once "$IF0"
  bind_rndis_once "$IF1"
  d0="$(driver_of "$IF0")"
  d1="$(driver_of "$IF1")"
  if [ "$d0" = "rndis_host" ] && [ "$d1" = "rndis_host" ]; then
    log "rndis_host bound to both"
    break
  fi
  sleep 0.25
done

# find net iface
find_net() {
  ls -1 "/sys/bus/usb/devices/$IF0/net" 2>/dev/null | head -n1 || true
}

IFACE="$(find_net)"
if [ -z "$IFACE" ]; then
  IFACE="$(ls -1 "/sys/bus/usb/devices/$IF1/net" 2>/dev/null | head -n1 || true)"
fi

# If still no net, do USB reset and try once more
if [ -z "$IFACE" ]; then
  log "no net iface yet -> USB reset $BASE"
  echo -n "$BASE" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null || true
  sleep 2
  echo -n "$BASE" > /sys/bus/usb/drivers/usb/bind 2>/dev/null || true
  sleep 3

  # unbind both again + bind both again
  unbind_any "$IF0"
  unbind_any "$IF1"
  sleep 0.5

  for _ in $(seq 1 120); do
    bind_rndis_once "$IF0"
    bind_rndis_once "$IF1"
    IFACE="$(find_net)"
    [ -n "$IFACE" ] && break
    IFACE="$(ls -1 "/sys/bus/usb/devices/$IF1/net" 2>/dev/null | head -n1 || true)"
    [ -n "$IFACE" ] && break
    sleep 0.25
  done
fi

[ -n "$IFACE" ] || { log "ERROR: still no net iface (usb0)"; exit 0; }

log "net iface=$IFACE"

# rename to usb0 if needed
if [ "$IFACE" != "usb0" ] && ! ip link show usb0 >/dev/null 2>&1; then
  log "rename $IFACE -> usb0"
  ip link set "$IFACE" down 2>/dev/null || true
  ip link set "$IFACE" name usb0 2>/dev/null || true
  IFACE="usb0"
fi

log "DHCP on $IFACE"
ip link set "$IFACE" up 2>/dev/null || true
ip -4 addr flush dev "$IFACE" 2>/dev/null || true
busybox udhcpc -q -n -i "$IFACE" -T 3 -t 5 -s /usr/local/sbin/udhcpc-usb0-hook.sh || true

# keep eth0 fallback metric
ip -4 route replace default via 192.168.1.1 dev eth0 metric 300 2>/dev/null || true

usb0_ok && log "usb0 OK after fix" || log "usb0 still not OK (will retry later)"
exit 0
