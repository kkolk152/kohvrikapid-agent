"""Päikesepaneeli MPPT laadimiskontrolleri BLE-lugeja (Qoltec / Lumiax OEM).

Kaks operatsiooni:
  * ``scan(timeout)``      — leiab läheduses olevad BLE-seadmed (setup jaoks).
  * ``read_once(mac)``     — ühendub valitud seadmega, küsib live-frame'i ja parsib.

Protokoll (Lumiax/OEM MPPT, kinnitamata offsetid — hoiame ka raw_hex-i, et
serveris saaks hiljem parandada):
  NOTIFY  UUID  0000ff01-0000-1000-8000-00805f9b34fb
  WRITE   UUID  0000ff02-0000-1000-8000-00805f9b34fb
  GET_STATUS   fe 04 3030 002b <crc>  → ~92-baidine Modbus-vastus (01 04 ...).

Kontroller lubab korraga ainult ÜHE BLE-ühenduse (telefoni-äpp vs Pi).

`bleak` imporditakse laisalt, et moodul ei kukuks, kui teek pole paigaldatud
(nt ESP32-kappidel, kus solar pole kasutusel)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger("kohvrikapid-agent.solar")

NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
GET_STATUS = bytes.fromhex("fe043030002bab15")
VALID_HEADERS = (b"\x01\x03", b"\x01\x04")


class SolarUnavailable(RuntimeError):
    """bleak pole paigaldatud või BLE ei ole saadaval."""


def _require_bleak():
    try:
        import bleak  # noqa: F401
        return bleak
    except ImportError as e:  # pragma: no cover
        raise SolarUnavailable("bleak not installed") from e


# ---------- Parsimine ----------

def _u16(data: bytes, pos: int) -> Optional[int]:
    if pos + 2 > len(data):
        return None
    return int.from_bytes(data[pos:pos + 2], "big", signed=False)


def _s16(data: bytes, pos: int) -> Optional[int]:
    if pos + 2 > len(data):
        return None
    return int.from_bytes(data[pos:pos + 2], "big", signed=True)


def _scale(v: Optional[int], factor: float) -> Optional[float]:
    return None if v is None else round(v * factor, 3)


def parse_frame(data: bytes) -> dict:
    """Parsib live-frame'i väärtusteks. Tundmatu/lühikese frame'i puhul jätab
    väljad None-iks; raw_hex läheb serverisse alati."""
    out: dict = {"raw_hex": data.hex(), "ok": False}
    if len(data) < 82:
        out["reason"] = "too_short"
        return out
    out.update({
        "ok": True,
        "battery_soc_percent": data[46] if 46 < len(data) else None,
        "battery_voltage_v": _scale(_u16(data, 47), 0.01),
        "battery_current_a": _scale(_s16(data, 49), 0.01),
        "battery_temp_c": _scale(_u16(data, 17), 0.01),
        "pv_voltage_v": _scale(_u16(data, 63), 0.01),
        "pv_current_a": _scale(_s16(data, 65), 0.01),
        "pv_power_w": _scale(_u16(data, 67), 0.01),
        "pv_total_kwh": _scale(_u16(data, 73), 0.01),
        "load_voltage_v": _scale(_u16(data, 55), 0.01),
        "load_current_a": _scale(_s16(data, 57), 0.01),
        "load_power_w": _scale(_u16(data, 59), 0.01),
        "load_total_kwh": _scale(_u16(data, 79), 0.01),
    })
    return out


# ---------- Async operatsioonid ----------

async def _scan_async(timeout: float) -> list[dict]:
    bleak = _require_bleak()
    from bleak import BleakScanner
    found: list[dict] = []
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for address, item in devices.items():
        device, adv = item
        name = device.name or (adv.local_name if adv else None)
        found.append({"address": address, "name": name, "rssi": adv.rssi if adv else None})
    return found


async def _read_once_async(mac: str, connect_timeout: float) -> dict:
    _require_bleak()
    from bleak import BleakClient, BleakScanner

    dev = await BleakScanner.find_device_by_address(mac, timeout=connect_timeout)
    target = dev or mac  # BleakClient aktsepteerib ka MAC-stringi

    full = bytearray()
    done = asyncio.Event()

    def on_notify(_char, value: bytearray) -> None:
        nonlocal full
        chunk = bytes(value)
        if chunk.startswith(VALID_HEADERS) and len(chunk) > 2:
            full = bytearray(chunk)
        else:
            full.extend(chunk)
        if len(full) >= 3:
            expected = full[2] + 5  # id + fn + bytecount + payload + crc(2)
            if len(full) >= expected:
                done.set()

    async with BleakClient(target, timeout=connect_timeout) as client:
        await client.start_notify(NOTIFY_UUID, on_notify)
        await asyncio.sleep(0.3)
        try:
            await client.write_gatt_char(WRITE_UUID, GET_STATUS, response=False)
        except Exception:
            await client.write_gatt_char(WRITE_UUID, GET_STATUS, response=True)
        try:
            await asyncio.wait_for(done.wait(), timeout=8.0)
        finally:
            try:
                await client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass

    return parse_frame(bytes(full))


# ---------- Sünkroonsed wrapperid (agent-loop on sünkroonne) ----------

def _run(coro, hard_timeout: float):
    return asyncio.run(asyncio.wait_for(coro, timeout=hard_timeout))


def scan(timeout: float = 12.0) -> list[dict]:
    """Tagastab kandidaatseadmed. Tühja listi, kui bleak/BLE puudub."""
    try:
        return _run(_scan_async(timeout), hard_timeout=timeout + 8)
    except SolarUnavailable:
        log.warning("BLE-skann ebaõnnestus: bleak pole paigaldatud")
        return []
    except Exception as e:
        log.warning("BLE-skann ebaõnnestus: %s", e)
        return []


def read_once(mac: str, connect_timeout: float = 15.0) -> Optional[dict]:
    """Loeb ühe live-frame'i. Tagastab dict (väljad + raw_hex + ts) või None."""
    try:
        data = _run(_read_once_async(mac, connect_timeout), hard_timeout=connect_timeout + 12)
    except SolarUnavailable:
        log.warning("BLE-lugem ebaõnnestus: bleak pole paigaldatud")
        return None
    except Exception as e:
        log.warning("BLE-lugem ebaõnnestus (%s): %s", mac, e)
        return None
    data["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return data
