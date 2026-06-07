"""Network mode tuvastus + telemeetria.

Pi agent võib joosta kahes võrgurežiimis (otsus tehakse võrgu boot-i ajal
``eth0-mode.sh`` ja ``udhcpc-usb0`` skriptide poolt, **mitte siin** — see
moodul ainult tuvastab praeguse seisu ja raporteerib platformile).

Režiimid:

1. **cellular_router** — Teltonika Calyx 4G HAT+ on küljes (usb0 olemas).
   Pi kasutab usb0-d upstream-iks (default route metric=50) ja jagab eth0-st
   netti laiali (NAT + dnsmasq DHCP alamvõrgus 192.168.100.0/24).
   Lukukontrollereid otsitakse selles alamvõrgus.

2. **ethernet_client** — usb0 puudub. eth0 on DHCP klient (route metric=300).
   Lukukontrollereid otsitakse selles alamvõrgus, mille DHCP server eth0-le andis.

3. **unknown** — kumbki ei tööta veel (boot-i ajal või võrk maas).
"""
from __future__ import annotations
import ipaddress
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

USB_IFACE = "usb0"           # 4G HAT ECM/RNDIS liides
ETH_IFACE = "eth0"           # LAN
USB_GATEWAY = "192.168.200.1"   # Modemi sisemine gateway IP
LAN_ROUTER_NETWORK = "192.168.100.0/24"  # Pi=192.168.100.1 router-režiimis


def hat_present() -> bool:
    """Teltonika Calyx 4G HAT+ on küljes (usb0 liides tekkis)."""
    return Path(f"/sys/class/net/{USB_IFACE}").exists()


def current_network_mode() -> str:
    """Tagasta praegune režiim: 'cellular_router' | 'ethernet_client' | 'unknown'."""
    default_iface = _default_route_iface()
    if default_iface == USB_IFACE:
        return "cellular_router"
    if default_iface and default_iface.startswith(("eth", "end", "enp")):
        return "ethernet_client"
    if hat_present():
        # HAT on küljes, aga route veel pole — boot vahepeal
        return "cellular_router"
    return "unknown"


def _default_route_iface() -> Optional[str]:
    if not shutil.which("ip"):
        return None
    try:
        out = subprocess.run(["ip", "-j", "route", "show", "default"], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    # Kõige madalama metric'iga default route
    best: Optional[dict] = None
    for route in data:
        if route.get("dst") != "default":
            continue
        m = route.get("metric", 0) or 0
        if best is None or m < (best.get("metric", 0) or 0):
            best = route
    return best.get("dev") if best else None


def discovery_subnet() -> Optional[str]:
    """Mis CIDR-i sees Pi peab lukukontrollereid otsima.

    Mõlemas režiimis otsime eth0 alamvõrgus.
    cellular_router: Pi on 192.168.100.1/24 → skaneerime selle.
    ethernet_client: eth0 sai DHCP-ga IP → skaneerime selle subneti.
    """
    return _iface_cidr(ETH_IFACE)


def _iface_cidr(iface: str) -> Optional[str]:
    if not shutil.which("ip"):
        return None
    try:
        out = subprocess.run(["ip", "-j", "addr", "show", "dev", iface], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    for entry in data:
        for addr in entry.get("addr_info", []):
            if addr.get("family") == "inet":
                ip = addr.get("local")
                prefix = addr.get("prefixlen")
                if ip and prefix is not None:
                    try:
                        net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
                        return str(net)
                    except ValueError:
                        return None
    return None


def gather_network_state() -> dict:
    """Telemeetria long-poll-i ``extra.network`` jaoks."""
    state: dict = {
        "hat_present": hat_present(),
        "mode": current_network_mode(),
    }
    subnet = discovery_subnet()
    if subnet:
        state["discovery_subnet"] = subnet
    usb_ip = _iface_ip(USB_IFACE)
    if usb_ip:
        state["usb0_ip"] = usb_ip
    eth_ip = _iface_ip(ETH_IFACE)
    if eth_ip:
        state["eth0_ip"] = eth_ip
    watchdog = _read_watchdog_state()
    if watchdog:
        state["watchdog"] = watchdog
    return state


def _iface_ip(iface: str) -> Optional[str]:
    if not Path(f"/sys/class/net/{iface}").exists():
        return None
    if not shutil.which("ip"):
        return None
    try:
        out = subprocess.run(["ip", "-j", "addr", "show", "dev", iface], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    for entry in data:
        for addr in entry.get("addr_info", []):
            if addr.get("family") == "inet":
                return addr.get("local")
    return None


def _read_watchdog_state() -> Optional[dict]:
    """Loe 4g-watchdog-i hetkeolekut /run-st."""
    fail_path = Path("/run/4g-watchdog.fail")
    ts_path = Path("/run/4g-watchdog.ts")
    if not fail_path.exists() and not ts_path.exists():
        return None
    result: dict = {}
    if fail_path.exists():
        try:
            result["fail_count"] = int(fail_path.read_text().strip())
        except (ValueError, OSError):
            pass
    if ts_path.exists():
        try:
            result["last_reset_ts"] = int(ts_path.read_text().strip())
        except (ValueError, OSError):
            pass
    return result or None
