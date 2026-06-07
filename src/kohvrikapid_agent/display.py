"""Esimese-käivituse ekraan: kui Pi pole veel claim-itud, näita seerianumber + QR."""
from __future__ import annotations
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STATE_PATH = Path("/var/lib/kohvrikapid-agent/display_state.json")
FRAMEBUFFER_PATH = Path("/dev/fb0")


def display_available() -> bool:
    """Tuvasta kas Pi-l on füüsiline ekraan (framebuffer olemas ja avaneb).

    Kasutatakse autodetect-iks: kaks Pi varianti (ekraaniga ja ilma)
    jagavad sama agent koodi. Kui /dev/fb0 olemas ja avaneb (õigused dialout/video
    grupi kaudu), siis renderdame; muidu agent jookseb headless.
    """
    if not FRAMEBUFFER_PATH.exists():
        return False
    try:
        fd = os.open(str(FRAMEBUFFER_PATH), os.O_RDONLY | os.O_NONBLOCK)
        os.close(fd)
        return True
    except OSError as e:
        log.debug("Framebuffer olemas, aga ei avane: %s", e)
        return False


def write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def claim_state(serial: str, server_url: str, agent_version: str, firmware_version: Optional[str], network_info: dict) -> dict:
    claim_url = f"{server_url.rstrip('/')}/devices?serial={serial}"
    return {
        "view": "UNCLAIMED",
        "title": "Kohvrikapid",
        "message": "Ootan administraatori sidumist",
        "lines": [
            f"Seerianumber: {serial}",
            f"Tarkvara: agent {agent_version} / fw {firmware_version or '—'}",
            f"Võrk: {network_info.get('ip', '—')} ({network_info.get('iface', '—')})",
        ],
        "qr_url": claim_url,
        "qr_label": f"Skanni või ava: {claim_url}",
    }


def ready_state(cabinet_name: str, cabinet_kind: str, slot_status: dict | None = None) -> dict:
    return {
        "view": "READY",
        "title": cabinet_name,
        "message": "Tere tulemast!",
        "lines": [],
        "slot_status": slot_status or {},
    }


def render_to_framebuffer(state: dict) -> None:
    """Reaalne ekraani-render. Algselt: log + saada signal mock-display deemonile.

    Tegelik graafiline render Pi puhul kasutab pygame (vt pyproject extras=display)
    või /dev/fb0 otse. Praegu logitakse state ja kirjutatakse fail; eraldi
    display-protsess saab state-i ekraanile renderdada."""
    write_state(state)
    log.info("display: %s — %s", state.get("view"), state.get("message"))


def gather_network_info() -> dict:
    info: dict = {}
    if shutil.which("ip"):
        try:
            out = subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True, timeout=3)
            if out.returncode == 0:
                data = json.loads(out.stdout)
                for iface in data:
                    if iface.get("operstate") != "UP" or iface.get("ifname") == "lo":
                        continue
                    for addr in iface.get("addr_info", []):
                        if addr.get("family") == "inet":
                            info["iface"] = iface["ifname"]
                            info["ip"] = addr["local"]
                            return info
        except Exception:
            pass
    return info
