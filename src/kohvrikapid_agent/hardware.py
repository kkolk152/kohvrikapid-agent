"""Riistvara info ja RS485 lukukontrolleri abifunktsioonid."""
from __future__ import annotations
import logging
import platform
import shutil
import subprocess
from typing import Optional

log = logging.getLogger(__name__)


def gather_hardware_info() -> dict:
    info: dict = {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Model"):
                    info["model"] = line.split(":", 1)[1].strip()
                    break
    except FileNotFoundError:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    info["ram_mb"] = kb // 1024
                    break
    except FileNotFoundError:
        pass
    if shutil.which("vcgencmd"):
        try:
            out = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=2)
            if out.returncode == 0 and "temp=" in out.stdout:
                info["temperature_c"] = float(out.stdout.strip().split("=")[1].rstrip("'C"))
        except Exception:
            pass
    return info


def gather_telemetry() -> dict:
    """Kerged dünaamilised andmed — sees long-poll-i `extra` payloadi."""
    extra: dict = {}
    try:
        with open("/proc/loadavg") as f:
            extra["loadavg"] = f.read().split()[0]
    except FileNotFoundError:
        pass
    return extra


def send_rs485_packet(port: str, baud: int, hex_string: str) -> Optional[bytes]:
    """Saada NCU/KR-BU pakett RS485-le. Vastus tagastatakse esimese 64 bait-i ulatuses."""
    try:
        import serial  # type: ignore
    except ImportError:
        log.error("pyserial puudub — paigalda see kõigepealt")
        return None
    bytes_to_send = bytes(int(b, 16) for b in hex_string.split() if b)
    try:
        with serial.Serial(port, baudrate=baud, timeout=1.0) as ser:
            ser.write(bytes_to_send)
            return ser.read(64)
    except Exception as e:
        log.error("RS485 saatmine ebaõnnestus: %s", e)
        return None
