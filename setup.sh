#!/usr/bin/env bash
# =====================================================================
# Kohvrikapid — MANUAALNE täisseadistus tavalise (stock) Raspberry Pi OS peal.
#
# Kasuta pärast stock Raspberry Pi OS Lite/Desktop flashimist + esimest boot'i.
# Vajab internetti (WiFi/eth/4G) ja root'i.
#
#   1) Flashi stock Pi OS Lite (Raspberry Pi Imager -> vali WiFi/kasutaja/SSH ⚙).
#   2) Boot + SSH sisse.
#   3) Kopeeri see fail Pi-le ja jooksuta:
#         sudo bash setup.sh
#
# Paigaldab: Kohvrikapid agent (+ 4G/eth võrk + kiosk) · Raspberry Pi Connect ·
#            4G/eth re-tuvastus (hotplug) · ekraani-tuvastus (kiosk ainult ekraaniga).
# Self-contained — ei vaja teisi repo-faile.
# =====================================================================
set -euo pipefail
[ "$(id -u)" = "0" ] || { echo "Jooksuta root/sudo-ga:  sudo bash setup.sh" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive

INSTALL_DIR=/opt/kohvrikapid-agent
CU="${SUDO_USER:-pi}"

echo "== 1/4: Kohvrikapid agent (ametlik installer: agent + 4G/eth võrk + kiosk) =="
# ENABLE_KIOSK=1 (vaikimisi) paigaldab ka kiosk-UI (chromium). server_url = ctr-locker.kakuweb.ee.
curl -fsSL https://raw.githubusercontent.com/kkolk152/kohvrikapid-agent/main/install.sh | bash

echo "== 2/4: SSH + Raspberry Pi Connect (turvaline kaug-ligipääs, ka 4G/NAT taga) =="
apt-get update -qq || true
apt-get install -y --no-install-recommends openssh-server rpi-connect-lite 2>/dev/null || \
	apt-get install -y --no-install-recommends openssh-server rpi-connect 2>/dev/null || true
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd 2>/dev/null || true
loginctl enable-linger "$CU" 2>/dev/null || { install -d /var/lib/systemd/linger; touch "/var/lib/systemd/linger/$CU"; }
if [ -f /usr/lib/systemd/user/rpi-connect.service ]; then
	install -d -o "$CU" -g "$CU" "/home/$CU/.config/systemd/user/default.target.wants" 2>/dev/null || true
	ln -sf /usr/lib/systemd/user/rpi-connect.service \
		"/home/$CU/.config/systemd/user/default.target.wants/rpi-connect.service" 2>/dev/null || true
	chown -R "$CU:$CU" "/home/$CU/.config" 2>/dev/null || true
fi

echo "== 3/4: 4G/eth re-tuvastus (hotplug + perioodiline) =="
cat > /etc/udev/rules.d/99-kohvrikapid-4g.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="net", KERNEL=="usb0", RUN+="/usr/local/sbin/calyx-up.sh"
SUBSYSTEM=="usb", ATTR{idVendor}=="1d12", ATTR{idProduct}=="0101", RUN+="/usr/local/sbin/calyx-up.sh"
EOF
cat > /usr/local/sbin/kohvrikapid-netcheck.sh <<'EOF'
#!/usr/bin/env bash
[ -x /usr/local/sbin/calyx-up.sh ] && /usr/local/sbin/calyx-up.sh || true
[ -x /usr/local/sbin/eth0-mode.sh ] && /usr/local/sbin/eth0-mode.sh || true
EOF
chmod 755 /usr/local/sbin/kohvrikapid-netcheck.sh
cat > /etc/systemd/system/kohvrikapid-netcheck.service <<'EOF'
[Unit]
Description=Kohvrikapid võrgu re-tuvastus (4G/eth)
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/kohvrikapid-netcheck.sh
EOF
cat > /etc/systemd/system/kohvrikapid-netcheck.timer <<'EOF'
[Unit]
Description=Kohvrikapid võrgu re-tuvastus perioodiliselt (4G/eth)
[Timer]
OnBootSec=25
OnUnitActiveSec=120
[Install]
WantedBy=timers.target
EOF
systemctl enable kohvrikapid-netcheck.timer 2>/dev/null || true

echo "== 4/4: Ekraani-tuvastus → kiosk ainult ekraani olemasolul =="
cat > /usr/local/sbin/kohvrikapid-display-detect.sh <<'EOF'
#!/usr/bin/env bash
OUT=/run/kohvrikapid-display
st="none"; ty=""
for s in /sys/class/drm/*/status; do
  [ -e "$s" ] || continue
  if [ "$(cat "$s" 2>/dev/null)" = "connected" ]; then
    st="connected"
    case "$s" in *HDMI*) ty="${ty:+$ty,}hdmi";; *DSI*) ty="${ty:+$ty,}dsi";; *DPI*) ty="${ty:+$ty,}dpi";; esac
  fi
done
if grep -qiE '^[[:space:]]*dtoverlay=.*(dpi|vc4-kms-dpi|piscreen|waveshare|goodix|ft5406|edt-ft5x06)' /boot/firmware/config.txt 2>/dev/null; then
  st="connected"; ty="${ty:+$ty,}dpi"
fi
echo "display=$st type=${ty:-none} ts=$(date -u +%FT%TZ)" > "$OUT"
logger -t kohvrikapid-display "display=$st type=${ty:-none}"
# Ekraani olemasolul käivita kiosk (chromium näitab agendi setup/ühenduse/staatus lehte)
if [ "$st" = "connected" ] && systemctl list-unit-files kohvrikapid-kiosk.service >/dev/null 2>&1; then
  systemctl start kohvrikapid-kiosk.service 2>/dev/null || true
fi
EOF
chmod 755 /usr/local/sbin/kohvrikapid-display-detect.sh
cat > /etc/systemd/system/kohvrikapid-display.service <<'EOF'
[Unit]
Description=Kohvrikapid ekraani tuvastus (HDMI/DSI/DPI) + kiosk gate
After=multi-user.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/kohvrikapid-display-detect.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl enable kohvrikapid-display.service 2>/dev/null || true
# kiosk EI käivitu ise — ainult display-detect kaudu (headless Pi jääb ilma chromiumita)
systemctl disable kohvrikapid-kiosk.service 2>/dev/null || true

systemctl daemon-reload 2>/dev/null || true
cat <<'EOF'

=== VALMIS ===
  1. sudo reboot
  2. Kontrolli platvormil (Seadmed), et Pi registreerus -> paarita kapiga.
  3. Raspberry Pi Connect: jooksuta 'rpi-connect signin' -> ava link -> logi Raspberry Pi ID-ga.
  4. Ekraaniga Pi: kiosk (setup/staatus leht) käivitub automaatselt boot'il.
  5. Soovi korral tee sellest SD-st korduvkasutatav .img (dd + pishrink).
EOF
