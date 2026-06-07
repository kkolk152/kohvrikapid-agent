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
    """Renderda state Pi DSI/HDMI ekraanile (/dev/fb0).

    Toimib Pi Touchscreen 2 (DSI), 7" HDMI ekraani ja teiste fb0-baseeritud
    ekraanidega. Salvestab state-i ka JSON-i (debug + integration). Kui PIL/numpy
    puuduvad või fb info pole loetav, kukub graceful tagasi ainult JSON-i peale.
    """
    write_state(state)
    log.info("display: %s — %s", state.get("view"), state.get("message"))
    try:
        fb_render_state(state)
    except Exception as e:
        log.warning("FB render ebaõnnestus, ainult JSON kirjutatud: %s", e)


def fb_info() -> Optional[dict]:
    """Loe /sys/class/graphics/fb0/ — width, height, bpp, line_length."""
    sysfb = Path("/sys/class/graphics/fb0")
    if not sysfb.exists():
        return None
    try:
        vsize = (sysfb / "virtual_size").read_text().strip()
        bpp = int((sysfb / "bits_per_pixel").read_text().strip())
        line_length = int((sysfb / "stride").read_text().strip())
        w, h = (int(x) for x in vsize.split(","))
        return {"width": w, "height": h, "bpp": bpp, "line_length": line_length}
    except Exception as e:
        log.debug("fb_info viga: %s", e)
        return None


def _load_font(size: int):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _build_image(state: dict, width: int, height: int):
    """Joonista state PIL Image objektile."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), (12, 18, 38))  # tume sinine
    draw = ImageDraw.Draw(img)

    portrait = height > width
    margin = max(24, min(width, height) // 20)
    title_size = 56 if portrait else 48
    body_size = 32 if portrait else 28
    small_size = 24

    title_font = _load_font(title_size)
    body_font = _load_font(body_size)
    small_font = _load_font(small_size)

    y = margin
    title = state.get("title", "Kohvrikapid")
    draw.text((margin, y), title, fill=(255, 255, 255), font=title_font)
    y += int(title_size * 1.5)

    message = state.get("message", "")
    if message:
        draw.text((margin, y), message, fill=(200, 220, 255), font=body_font)
        y += int(body_size * 1.5)

    for line in state.get("lines", []) or []:
        draw.text((margin, y), str(line), fill=(170, 180, 200), font=small_font)
        y += int(small_size * 1.4)

    qr_url = state.get("qr_url")
    if qr_url:
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="white", back_color="black").convert("RGB")
            target = min(width, height) // 2
            qr_img = qr_img.resize((target, target), Image.NEAREST)
            if portrait:
                qx = (width - target) // 2
                qy = max(y + margin, height - target - margin * 3)
            else:
                qx = width - target - margin
                qy = (height - target) // 2
            img.paste(qr_img, (qx, qy))
            label = state.get("qr_label") or qr_url
            label_text = label[:60]
            tw = draw.textlength(label_text, font=small_font)
            lx = max(margin, qx + (target - int(tw)) // 2)
            ly = qy + target + 8
            if ly + small_size <= height - margin:
                draw.text((lx, ly), label_text, fill=(220, 230, 240), font=small_font)
        except Exception as e:
            log.debug("QR genereerimine ebaõnnestus: %s", e)
    return img


def fb_render_state(state: dict) -> None:
    info = fb_info()
    if not info:
        log.debug("fb_info pole loetav")
        return
    try:
        import numpy as np
    except ImportError:
        log.warning("numpy puudub — paigalda venv-i")
        return
    w, h, bpp = info["width"], info["height"], info["bpp"]
    line_length = info.get("line_length") or (w * bpp // 8)
    img = _build_image(state, w, h)
    arr = np.array(img.convert("RGB"))
    if bpp == 16:
        r = (arr[..., 0].astype(np.uint16) & 0xF8) << 8
        g = (arr[..., 1].astype(np.uint16) & 0xFC) << 3
        b = (arr[..., 2].astype(np.uint16) >> 3)
        pixel = (r | g | b).astype(np.uint16)
        row_bytes = w * 2
        with open(FRAMEBUFFER_PATH, "rb+") as fb:
            for y in range(h):
                fb.seek(y * line_length)
                fb.write(pixel[y].tobytes()[:row_bytes])
    elif bpp == 32:
        bgra = np.zeros((h, w, 4), dtype=np.uint8)
        bgra[..., 0] = arr[..., 2]  # B
        bgra[..., 1] = arr[..., 1]  # G
        bgra[..., 2] = arr[..., 0]  # R
        bgra[..., 3] = 255          # A
        row_bytes = w * 4
        with open(FRAMEBUFFER_PATH, "rb+") as fb:
            for y in range(h):
                fb.seek(y * line_length)
                fb.write(bgra[y].tobytes()[:row_bytes])
    else:
        log.warning("Toetamata fb bpp=%s — jätan vahele", bpp)


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
