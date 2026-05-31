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
        elif action == "sync_stock":
            result["note"] = "no-op (stock state read on demand)"
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
    raw_hex = payload.get("raw_hex")
    if raw_hex and config.serial_port:
        reply = send_rs485_packet(config.serial_port, config.serial_baud, raw_hex)
        return {"raw_reply_hex": reply.hex(" ") if reply else None}
    # TODO: GPIO relay-pin pulse for non-NCU setups
    return {"note": "no serial_port configured — open_slot is no-op"}


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


def run() -> None:
    config = AgentConfig.load()
    secrets = AgentSecrets.load()
    serial = secrets.serial or read_or_create_serial()
    hw_info = gather_hardware_info()

    log.info("Kohvrikapid agent %s käivitub (serial=%s, server=%s)", __version__, serial, config.server_url)

    with AgentClient(server_url=config.server_url) as client_:
        client = client_
        secrets = ensure_registered(client, secrets, serial, hw_info)

        # First display state
        if config.display_enabled:
            render_to_framebuffer(claim_state(
                serial=serial,
                server_url=config.server_url,
                agent_version=__version__,
                firmware_version=_firmware_version(),
                network_info=gather_network_info(),
            ))

        backoff = config.long_poll_retry_seconds
        while _running:
            extra = {
                "telemetry": gather_telemetry(),
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

            # Update display based on paired state
            if config.display_enabled:
                cfg_part = resp.get("config", {})
                if cfg_part.get("paired"):
                    render_to_framebuffer(ready_state(
                        cabinet_name=cfg_part.get("cabinet_name", "Kohvrikapp"),
                        cabinet_kind=cfg_part.get("cabinet_kind", "vending"),
                    ))
                else:
                    render_to_framebuffer(claim_state(
                        serial=serial,
                        server_url=config.server_url,
                        agent_version=__version__,
                        firmware_version=_firmware_version(),
                        network_info=gather_network_info(),
                    ))

            handle_long_poll_response(client, resp, config)


def main() -> int:
    try:
        run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
