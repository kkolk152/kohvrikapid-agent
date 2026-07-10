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

# Get-status käsud, mida proovime (Lumiax/OEM Modbus). Kui seade pushib andmeid
# ise (paljud ffe0-teenusega mudelid), saame frame'i ka ilma käsuta.
GET_STATUS_COMMANDS = (
    bytes.fromhex("fe043030002bab15"),
    bytes.fromhex("fe0430000022e1d5"),
)
VALID_HEADERS = (b"\x01\x03", b"\x01\x04")

# Eelistusjärjekord kui mitu vendor-karakteristikut sobib (16-bit lühivorm).
_NOTIFY_PREF = ("ffe4", "ff01", "fff1", "ffe1", "fff4")
_WRITE_PREF = ("ffe1", "ff02", "fff2", "ffe4", "fff1")


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


def _pick_chars(client):
    """Tuvastab AUTOMAATSELT notify + write karakteristikud vendor-teenustest
    (ffxx). Töötab nii ffe4/ffe1 (SY-GM24) kui ff01/ff02 jt mudelitega — pole
    vaja käsitsi UUID-e seadistada."""
    notifies: list[str] = []
    writes: list[str] = []
    for service in client.services:
        for ch in service.characteristics:
            u = ch.uuid.lower()
            if not u[4:8].startswith("ff"):
                continue  # jäta standard-GATT (2axx) vahele
            props = set(ch.properties)
            if props & {"notify", "indicate"}:
                notifies.append(u)
            if props & {"write", "write-without-response"}:
                writes.append(u)

    def _best(cands: list[str], pref: tuple[str, ...]) -> Optional[str]:
        for p in pref:
            for u in cands:
                if u[4:8] == p:
                    return u
        return cands[0] if cands else None

    return _best(notifies, _NOTIFY_PREF), _best(writes, _WRITE_PREF)


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
        if full[:2] in VALID_HEADERS and len(full) >= 3:
            if len(full) >= full[2] + 5:  # id + fn + bytecount + payload + crc(2)
                done.set()
        elif len(full) >= 90:
            done.set()

    async with BleakClient(target, timeout=connect_timeout) as client:
        notify_uuid, write_uuid = _pick_chars(client)
        if not notify_uuid:
            raise SolarUnavailable("ühtki notify-karakteristikut ei leitud")
        log.info("Solar BLE: notify=%s write=%s", notify_uuid, write_uuid)
        await client.start_notify(notify_uuid, on_notify)
        await asyncio.sleep(0.3)

        # Proovi get-status käske; kui seade pushib ise, saame frame'i niikuinii.
        if write_uuid:
            for cmd in GET_STATUS_COMMANDS:
                try:
                    await client.write_gatt_char(write_uuid, cmd, response=False)
                except Exception:
                    try:
                        await client.write_gatt_char(write_uuid, cmd, response=True)
                    except Exception:
                        pass
                try:
                    await asyncio.wait_for(done.wait(), timeout=3.0)
                    break
                except asyncio.TimeoutError:
                    continue

        if not done.is_set():
            # auto-push seadmed vajavad ainult subscribimist
            try:
                await asyncio.wait_for(done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

        try:
            await client.stop_notify(notify_uuid)
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
    if not data.get("raw_hex"):
        return None  # frame'i ei tulnud — ära postita tühja
    data["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return data
