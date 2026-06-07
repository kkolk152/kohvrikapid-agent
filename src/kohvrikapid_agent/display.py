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
    """Hangi framebuffer info — proovi mitut allikat järjestikku.

    1. ioctl FBIOGET_VSCREENINFO + FBIOGET_FSCREENINFO (kõige stabiilsem,
       töötab ka RP1 DSI-l kus sysfs entry-d on restricted)
    2. /sys/class/graphics/fb0/* (vanade Pi mudelite jaoks)
    3. fbset -i parse (kui fbset on installeeritud)
    """
    info = _fb_info_via_ioctl()
    if info:
        return info
    info = _fb_info_via_sysfs()
    if info:
        return info
    return _fb_info_via_fbset()


def _fb_info_via_ioctl() -> Optional[dict]:
    try:
        import ctypes
        import fcntl
    except ImportError:
        return None
    if not FRAMEBUFFER_PATH.exists():
        return None

    class _Bitfield(ctypes.Structure):
        _fields_ = [
            ("offset", ctypes.c_uint32),
            ("length", ctypes.c_uint32),
            ("msb_right", ctypes.c_uint32),
        ]

    class _VarScreenInfo(ctypes.Structure):
        _fields_ = [
            ("xres", ctypes.c_uint32),
            ("yres", ctypes.c_uint32),
            ("xres_virtual", ctypes.c_uint32),
            ("yres_virtual", ctypes.c_uint32),
            ("xoffset", ctypes.c_uint32),
            ("yoffset", ctypes.c_uint32),
            ("bits_per_pixel", ctypes.c_uint32),
            ("grayscale", ctypes.c_uint32),
            ("red", _Bitfield),
            ("green", _Bitfield),
            ("blue", _Bitfield),
            ("transp", _Bitfield),
            ("nonstd", ctypes.c_uint32),
            ("activate", ctypes.c_uint32),
            ("height", ctypes.c_uint32),
            ("width", ctypes.c_uint32),
            ("accel_flags", ctypes.c_uint32),
            ("pixclock", ctypes.c_uint32),
            ("left_margin", ctypes.c_uint32),
            ("right_margin", ctypes.c_uint32),
            ("upper_margin", ctypes.c_uint32),
            ("lower_margin", ctypes.c_uint32),
            ("hsync_len", ctypes.c_uint32),
            ("vsync_len", ctypes.c_uint32),
            ("sync", ctypes.c_uint32),
            ("vmode", ctypes.c_uint32),
            ("rotate", ctypes.c_uint32),
            ("colorspace", ctypes.c_uint32),
            ("reserved", ctypes.c_uint32 * 4),
        ]

    class _FixScreenInfo(ctypes.Structure):
        _fields_ = [
            ("id", ctypes.c_char * 16),
            ("smem_start", ctypes.c_ulong),
            ("smem_len", ctypes.c_uint32),
            ("type", ctypes.c_uint32),
            ("type_aux", ctypes.c_uint32),
            ("visual", ctypes.c_uint32),
            ("xpanstep", ctypes.c_uint16),
            ("ypanstep", ctypes.c_uint16),
            ("ywrapstep", ctypes.c_uint16),
            ("line_length", ctypes.c_uint32),
            ("mmio_start", ctypes.c_ulong),
            ("mmio_len", ctypes.c_uint32),
            ("accel", ctypes.c_uint32),
            ("capabilities", ctypes.c_uint16),
            ("reserved", ctypes.c_uint16 * 2),
        ]

    FBIOGET_VSCREENINFO = 0x4600
    FBIOGET_FSCREENINFO = 0x4602
    try:
        fd = os.open(str(FRAMEBUFFER_PATH), os.O_RDONLY)
    except OSError as e:
        log.debug("fb_info_ioctl: open ebaõnnestus: %s", e)
        return None
    try:
        vinfo = _VarScreenInfo()
        finfo = _FixScreenInfo()
        fcntl.ioctl(fd, FBIOGET_VSCREENINFO, vinfo)
        fcntl.ioctl(fd, FBIOGET_FSCREENINFO, finfo)
        return {
            "width": int(vinfo.xres),
            "height": int(vinfo.yres),
            "bpp": int(vinfo.bits_per_pixel),
            "line_length": int(finfo.line_length),
            "red_offset": int(vinfo.red.offset),
            "green_offset": int(vinfo.green.offset),
            "blue_offset": int(vinfo.blue.offset),
            "source": "ioctl",
        }
    except Exception as e:
        log.debug("fb_info_ioctl ebaõnnestus: %s", e)
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _fb_info_via_sysfs() -> Optional[dict]:
    sysfb = Path("/sys/class/graphics/fb0")
    if not sysfb.exists():
        return None
    try:
        vsize = (sysfb / "virtual_size").read_text().strip()
        bpp = int((sysfb / "bits_per_pixel").read_text().strip())
        line_length = int((sysfb / "stride").read_text().strip())
        w, h = (int(x) for x in vsize.split(","))
        return {"width": w, "height": h, "bpp": bpp, "line_length": line_length, "source": "sysfs"}
    except Exception as e:
        log.debug("fb_info_sysfs viga: %s", e)
        return None


def _fb_info_via_fbset() -> Optional[dict]:
    if not shutil.which("fbset"):
        return None
    try:
        out = subprocess.run(["fbset", "-i"], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    width = height = bpp = line_length = None
    for line in out.stdout.splitlines():
        ls = line.strip()
        if ls.startswith("geometry"):
            parts = ls.split()
            try:
                width = int(parts[1]); height = int(parts[2]); bpp = int(parts[5])
            except (ValueError, IndexError):
                pass
        elif ls.startswith("LineLength"):
            try:
                line_length = int(ls.split(":", 1)[1].strip())
            except ValueError:
                pass
    if width and height and bpp:
        if not line_length:
            line_length = width * bpp // 8
        return {"width": width, "height": height, "bpp": bpp, "line_length": line_length, "source": "fbset"}
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
    img = Image.new("RGB", (width, height), (12, 18, 38))  # tume navy
    draw = ImageDraw.Draw(img)
    # Aktsentriba üleval — bränd
    draw.rectangle((0, 0, width, 8), fill=(56, 132, 255))

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
        log.warning("fb_render: fb_info ei suutnud lugeda (sysfs/ioctl/fbset kõik kukkusid) — render skip")
        return
    log.info(
        "fb_render: %dx%d @ %dbpp source=%s line_length=%d",
        info["width"], info["height"], info["bpp"], info.get("source"), info["line_length"],
    )
    try:
        import numpy as np
    except ImportError:
        log.warning("numpy puudub — paigalda venv-i")
        return
    w, h, bpp = info["width"], info["height"], info["bpp"]
    line_length = info.get("line_length") or (w * bpp // 8)
    try:
        img = _build_image(state, w, h)
    except Exception as e:
        log.error("PIL _build_image ebaõnnestus: %s", e)
        raise
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
        try:
            _write_full_buffer(bgra.tobytes(), w, h, line_length, row_bytes=w * 4)
        except PermissionError as e:
            log.error("fb_render: PermissionError /dev/fb0-le kirjutamisel: %s", e)
            raise
        except OSError as e:
            log.error("fb_render: OSError /dev/fb0 kirjutamisel: %s", e)
            raise
    else:
        log.warning("Toetamata fb bpp=%s — jätan vahele", bpp)


def _write_full_buffer(data: bytes, width: int, height: int, line_length: int, row_bytes: int) -> None:
    """Kirjuta terve framebuffer-i, ärata enne ekraan üles ja committi pärast.

    Mõned DRM-shim fb ajurid (drm-rp1-dsidrmf Pi 5-l) lähevad consoleblank
    timeout-iga energiasäästu. FBIOBLANK(UNBLANK) äratab paneeli üles enne
    write-i. FBIOPAN_DISPLAY pärast write-i sunnib commitida.
    """
    import fcntl
    FBIOGET_VSCREENINFO = 0x4600
    FBIOPAN_DISPLAY = 0x4606
    FBIOBLANK = 0x4611
    FB_BLANK_UNBLANK = 0

    fd = os.open(str(FRAMEBUFFER_PATH), os.O_RDWR)
    try:
        # Ärata ekraan üles
        try:
            fcntl.ioctl(fd, FBIOBLANK, FB_BLANK_UNBLANK)
        except Exception as e:
            log.debug("FBIOBLANK ebaõnnestus: %s", e)

        bytes_written = 0
        if row_bytes == line_length:
            # Stride match → ühe write-iga kogu buffer
            bytes_written = os.write(fd, data)
        else:
            # Stride padding — vaja rida-haaval
            for y in range(height):
                os.lseek(fd, y * line_length, os.SEEK_SET)
                start = y * row_bytes
                bytes_written += os.write(fd, data[start:start + row_bytes])

        # Sunni commit
        try:
            import ctypes
            class _VarScreenInfo(ctypes.Structure):
                _fields_ = [
                    ("xres", ctypes.c_uint32), ("yres", ctypes.c_uint32),
                    ("xres_virtual", ctypes.c_uint32), ("yres_virtual", ctypes.c_uint32),
                    ("xoffset", ctypes.c_uint32), ("yoffset", ctypes.c_uint32),
                    ("bits_per_pixel", ctypes.c_uint32), ("grayscale", ctypes.c_uint32),
                    ("padding", ctypes.c_uint8 * 200),  # ülejäänud — pole vaja täita
                ]
            vinfo = _VarScreenInfo()
            fcntl.ioctl(fd, FBIOGET_VSCREENINFO, vinfo)
            fcntl.ioctl(fd, FBIOPAN_DISPLAY, vinfo)
        except Exception as e:
            log.debug("FBIOPAN_DISPLAY ebaõnnestus (eiran): %s", e)

        try:
            os.fsync(fd)
        except OSError:
            pass
        log.info("fb_render: kirjutasin %d baiti /dev/fb0-le", bytes_written)
    finally:
        os.close(fd)


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
