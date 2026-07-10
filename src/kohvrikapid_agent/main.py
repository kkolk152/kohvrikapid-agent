"""Agent-loop: register-on-first-boot → infinite long-poll → handle commands & OTA."""
from __future__ import annotations
import logging
import signal
import sys
import time
from typing import Optional

import httpx

from . import __version__
from .client import AgentClient
from .config import AgentConfig, AgentSecrets, read_or_create_serial
from .display import claim_state, gather_network_info, ready_state, render_to_framebuffer
from .hardware import gather_hardware_info, gather_telemetry, send_rs485_packet
from . import discovery, network
from . import kiosk_server
from . import solar
from .ota import apply_firmware

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("kohvrikapid-agent")

_running = True


def _shutdown(_sig: int, _frame: object) -> None:
    global _running
    log.info("Saadi signaal — peatun")
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


def _firmware_version() -> Optional[str]:
    try:
        from . import __version__ as v
        return v
    except Exception:
        return None


def ensure_registered(client: AgentClient, secrets: AgentSecrets, serial: str, hardware_info: dict) -> AgentSecrets:
    if secrets.device_id and secrets.agent_token:
        client.device_id = secrets.device_id
        client.agent_token = secrets.agent_token
        return secrets
    log.info("Registreerin esmakordselt serial=%s", serial)
    response = client.register(
        serial=serial,
        hardware_kind="rpi",
        hardware_info=hardware_info,
        agent_version=__version__,
        firmware_version=_firmware_version(),
    )
    secrets.device_id = response["device_id"]
    secrets.agent_token = response["agent_token"]
    secrets.serial = serial
    secrets.save()
    log.info("Registreeritud: device_id=%s", secrets.device_id)
    return secrets


def handle_long_poll_response(client: AgentClient, response: dict, config: AgentConfig) -> None:
    # Firmware OTA
    fw_pending = response.get("firmware_pending")
    if fw_pending:
        log.info("OTA: server küsib paigaldada %s (%s)", fw_pending["version"], fw_pending["id"])
        apply_firmware(
            client,
            firmware_id=fw_pending["id"],
            sha256_expected=fw_pending["sha256"],
            size_expected=fw_pending["size"],
            install_command=config.firmware_install_command,
        )

    # Commands
    for cmd in response.get("commands", []):
        handle_command(client, cmd, config)


def handle_command(client: AgentClient, cmd: dict, config: AgentConfig) -> None:
    cid = cmd["id"]
    action = cmd["action"]
    payload = cmd.get("payload") or {}
    log.info("CMD %s action=%s payload=%s", cid, action, payload)

    status = "done"
    result: dict = {"action": action}

    try:
        if action == "open_slot":
            result.update(_open_slot(payload, config))
        elif action == "status":
            result.update(_query_status(payload, config))
        elif action == "lock_raw":
            result.update(_send_raw(payload, config))
        elif action == "query_locks":
            result.update(_query_locks(payload, config))
        elif action == "sync_stock":
            result["note"] = "no-op (stock state read on demand)"
        elif action == "solar_scan":
            result.update(_solar_scan(client, payload))
        elif action == "reboot":
            client.ack_command(cid, status="done", result={"note": "rebooting"})
            import subprocess
            subprocess.Popen(["systemctl", "reboot"])
            return
        else:
            log.warning("Tundmatu action %s", action)
            status = "failed"
            result["error"] = "unknown action"
    except Exception as e:
        log.exception("CMD ebaõnnestus")
        status = "failed"
        result["error"] = str(e)

    try:
        client.ack_command(cid, status=status, result=result)
    except Exception as e:
        log.error("ACK ebaõnnestus: %s", e)


def _open_slot(payload: dict, config: AgentConfig) -> dict:
    transport = payload.get("transport") or ("rs485_direct" if payload.get("raw_hex") else "gpio")
    if transport == "kr_bu":
        return _open_slot_via_kr_bu(payload)
    if transport == "rs485_direct":
        raw_hex = payload.get("raw_hex")
        if raw_hex and config.serial_port:
            reply = send_rs485_packet(config.serial_port, config.serial_baud, raw_hex)
            return {"transport": "rs485_direct", "raw_reply_hex": reply.hex(" ") if reply else None}
        return {"transport": "rs485_direct", "error": "no serial_port or raw_hex"}
    # gpio (relay): pulse a GPIO pin for unlock_ms milliseconds
    return _open_slot_via_gpio(payload)


def _open_slot_via_gpio(payload: dict) -> dict:
    pin = payload.get("gpio_pin")
    unlock_ms = int(payload.get("unlock_ms") or 550)
    if not isinstance(pin, int) or pin < 0:
        return {"transport": "gpio", "error": "no gpio_pin in payload"}
    try:
        import gpiod  # type: ignore  # Pi 5 — libgpiod v2
        with gpiod.request_lines(
            "/dev/gpiochip0",
            consumer="kohvrikapid-agent",
            config={pin: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT, output_value=gpiod.line.Value.ACTIVE)},
        ) as req:
            import time as _t
            _t.sleep(unlock_ms / 1000.0)
            req.set_value(pin, gpiod.line.Value.INACTIVE)
        return {"transport": "gpio", "pin": pin, "pulsed_ms": unlock_ms}
    except ImportError:
        log.warning("gpiod puudub — paigalda python3-gpiod")
        return {"transport": "gpio", "error": "gpiod not installed"}
    except Exception as e:
        log.error("GPIO pulse ebaõnnestus: %s", e)
        return {"transport": "gpio", "error": str(e)}


def _open_slot_via_kr_bu(payload: dict) -> dict:
    host = payload.get("bridge_host")
    port = int(payload.get("bridge_port") or 4196)
    raw_hex = payload.get("raw_hex")
    if not host or not raw_hex:
        return {"transport": "kr_bu", "error": "missing bridge_host or raw_hex"}
    try:
        import socket
        bytes_to_send = bytes(int(b, 16) for b in raw_hex.split() if b)
        # NB: KR-BU TCP klient — FINALLY close (vt platform_phase19 memo)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(3.0)
            s.connect((host, port))
            s.sendall(bytes_to_send)
            try:
                reply = s.recv(64)
            except socket.timeout:
                reply = b""
        finally:
            s.close()
        return {"transport": "kr_bu", "raw_reply_hex": reply.hex(" ") if reply else None}
    except Exception as e:
        log.error("KR-BU saatmine ebaõnnestus: %s", e)
        return {"transport": "kr_bu", "error": str(e)}


def _query_status(payload: dict, config: AgentConfig) -> dict:
    raw_hex = payload.get("raw_hex")
    if raw_hex and config.serial_port:
        reply = send_rs485_packet(config.serial_port, config.serial_baud, raw_hex)
        return {"raw_reply_hex": reply.hex(" ") if reply else None}
    return {"note": "no serial_port configured"}


def _send_raw(payload: dict, config: AgentConfig) -> dict:
    raw_hex = payload.get("raw_hex")
    if not raw_hex or not config.serial_port:
        return {"error": "raw_hex or serial_port missing"}
    reply = send_rs485_packet(config.serial_port, config.serial_baud, raw_hex)
    return {"raw_reply_hex": reply.hex(" ") if reply else None}


def _query_locks(payload: dict, config: AgentConfig) -> dict:
    """Saada NCU broadcast STATUS query (ADDR=0x00..0x0F või 0x64=kõik) ja
    loenda vastused. Tagastab leitud luku-numbrite listi.

    Payload: {"address": 0, "max_locks": 48}. Kui address puudub, saadame
    broadcasti.
    """
    address = int(payload.get("address", 0)) & 0xFF
    max_locks = int(payload.get("max_locks", 48))
    transport = payload.get("transport") or "rs485_direct"
    bridge_host = payload.get("bridge_host")
    bridge_port = int(payload.get("bridge_port") or 4196)
    found: list[int] = []

    def _send(frame_hex: str) -> bytes:
        if transport == "kr_bu" and bridge_host:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.settimeout(2.0)
                    s.connect((bridge_host, bridge_port))
                    s.sendall(bytes(int(b, 16) for b in frame_hex.split() if b))
                    return s.recv(256) or b""
                finally:
                    s.close()
            except Exception as e:
                log.debug("KR-BU query: %s", e)
                return b""
        if config.serial_port:
            reply = send_rs485_packet(config.serial_port, config.serial_baud, frame_hex)
            return reply or b""
        return b""

    # Käime üks-üks läbi 1..max_locks; lukk vastab status query-le (CMD=0x80)
    cmd = 0x80
    for lock_idx in range(max_locks):
        stx, etx, ask, datalen = 0x02, 0x03, 0x00, 0x00
        chk = (stx + address + lock_idx + cmd + ask + datalen + etx) & 0xFF
        frame = " ".join(f"{b:02x}" for b in (stx, address, lock_idx, cmd, ask, datalen, etx, chk))
        reply = _send(frame)
        # Vastus algab 0x02 ja LOCKNUM peab klappima
        if len(reply) >= 8 and reply[0] == 0x02 and reply[2] == lock_idx and reply[4] in (0x10, 0x11):
            found.append(lock_idx + 1)  # tagasi 1-based
    return {
        "address": address,
        "found_locks": found,
        "count": len(found),
        "transport": transport,
    }


def _solar_scan(client: AgentClient, payload: dict) -> dict:
    """`solar_scan` käsk: skanni BLE-seadmed ja postita kandidaadid serverisse."""
    timeout = float(payload.get("timeout_seconds") or 12)
    candidates = solar.scan(timeout=timeout)
    try:
        client.post_solar_scan_result(candidates)
    except Exception as e:
        log.warning("Solar scan-result post ebaõnnestus: %s", e)
    return {"candidates_found": len(candidates)}


def _maybe_read_solar(client: AgentClient, cfg_part: dict, last_ts: float) -> float:
    """Kui kapil on solar lubatud ja seade valitud, loeb MPPT frame'i
    `interval_seconds` tagant ja postitab serverisse. Konfig tuleb serverilt
    (build_agent_config → config.solar), seega Pi seadistab end ise."""
    solar_cfg = (cfg_part or {}).get("solar") or {}
    if not solar_cfg.get("enabled") or not solar_cfg.get("ble_mac"):
        return last_ts
    interval = max(15, int(solar_cfg.get("interval_seconds") or 60))
    now = time.time()
    if now - last_ts < interval:
        return last_ts
    reading = solar.read_once(solar_cfg["ble_mac"])
    if reading is None:
        return now  # märgime katse ajaks, et mitte iga loop'iga uuesti proovida
    payload = {k: v for k, v in reading.items() if k not in ("ok", "reason")}
    try:
        client.post_solar_reading(payload)
        log.info("Solar lugem saadetud: pv=%sW soc=%s%%",
                 reading.get("pv_power_w"), reading.get("battery_soc_percent"))
    except Exception as e:
        log.warning("Solar lugemi saatmine ebaõnnestus: %s", e)
    return now


def run() -> None:
    config = AgentConfig.load()
    secrets = AgentSecrets.load()
    serial = secrets.serial or read_or_create_serial()
    hw_info = gather_hardware_info()

    display_on = config.resolve_display_enabled()
    net_state = network.gather_network_state()
    kiosk_started = kiosk_server.start_kiosk_server()
    # Kui kiosk Chromium serveerib UI-d, ärme dubleerime fb-rendiga
    if kiosk_started:
        display_on = False
        log.info("kiosk HTTP server käivitatud — fb_render lülitatud välja")
    log.info(
        "Kohvrikapid agent %s käivitub (serial=%s, server=%s, display=%s, kiosk=%s, network=%s)",
        __version__, serial, config.server_url,
        "on" if display_on else "off",
        "on" if kiosk_started else "off",
        net_state.get("mode"),
    )

    last_discovery_ts = 0.0
    last_solar_ts = 0.0
    discovery_period = max(60, config.discovery_interval_minutes * 60)

    with AgentClient(server_url=config.server_url) as client_:
        client = client_
        secrets = ensure_registered(client, secrets, serial, hw_info)

        # First display state (kirjutab ka JSON-i, mida kiosk HTTP server loeb)
        initial_state = claim_state(
            serial=serial,
            server_url=config.server_url,
            agent_version=__version__,
            firmware_version=_firmware_version(),
            network_info=gather_network_info(),
            network_state=net_state,
        )
        if display_on:
            render_to_framebuffer(initial_state)
        else:
            # Kioski jaoks ainult kirjuta JSON-i, ära renderda fb-le
            from .display import write_state
            write_state(initial_state)

        backoff = config.long_poll_retry_seconds
        while _running:
            net_state = network.gather_network_state()
            # Aeg-ajalt skaneerime aktiivset alamvõrku Kerong kontrollerite leidmiseks
            if config.discovery_enabled and time.time() - last_discovery_ts > discovery_period:
                subnet = net_state.get("discovery_subnet")
                try:
                    discovery.scan_kerong(subnet)
                except Exception as e:
                    log.warning("Kerong discovery scan ebaõnnestus: %s", e)
                try:
                    discovery.scan_neighbors(subnet)
                except Exception as e:
                    log.warning("LAN neighbors scan ebaõnnestus: %s", e)
                last_discovery_ts = time.time()

            extra = {
                "telemetry": gather_telemetry(),
                "network": net_state,
                "discovery": discovery.gather_discovery_state(net_state.get("discovery_subnet")),
            }
            try:
                resp = client.long_poll(
                    agent_version=__version__,
                    firmware_version=_firmware_version(),
                    hardware_info=hw_info,
                    extra=extra,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    log.error("401 — token aegunud või tühistatud. Kustutan secrets ja registreerun uuesti.")
                    secrets = AgentSecrets()
                    secrets.save()
                    secrets = ensure_registered(client, secrets, serial, hw_info)
                    continue
                log.error("HTTP viga %s: %s", e.response.status_code, e)
                time.sleep(backoff)
                continue
            except httpx.RequestError as e:
                log.warning("Võrgu viga: %s — ootan %ds", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            backoff = config.long_poll_retry_seconds

            # Update display state — alati kirjutame JSON-i (kiosk loeb), fb ainult kui display_on
            cfg_part = resp.get("config", {})
            if cfg_part.get("paired"):
                new_state = ready_state(
                    cabinet_name=cfg_part.get("cabinet_name", "Kohvrikapp"),
                    cabinet_kind=cfg_part.get("cabinet_kind", "vending"),
                    network_state=net_state,
                    serial=serial,
                    agent_version=__version__,
                    tenant_config=cfg_part,
                )
            else:
                new_state = claim_state(
                    serial=serial,
                    server_url=config.server_url,
                    agent_version=__version__,
                    firmware_version=_firmware_version(),
                    network_info=gather_network_info(),
                    network_state=net_state,
                )
            if display_on:
                render_to_framebuffer(new_state)
            else:
                from .display import write_state
                write_state(new_state)

            last_solar_ts = _maybe_read_solar(client, cfg_part, last_solar_ts)

            handle_long_poll_response(client, resp, config)


def main() -> int:
    try:
        run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
