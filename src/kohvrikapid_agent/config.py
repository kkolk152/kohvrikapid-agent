"""Konfiguratsiooni ja saladuste haldus."""
from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomli_w

CONFIG_PATH = Path(os.environ.get("KOHVRIKAPID_CONFIG", "/etc/kohvrikapid-agent/config.toml"))
SECRETS_PATH = Path(os.environ.get("KOHVRIKAPID_SECRETS", "/etc/kohvrikapid-agent/secrets.toml"))
SERIAL_PATH = Path("/etc/kohvrikapid-agent/serial")


@dataclass
class AgentConfig:
    server_url: str = "https://kohvrikapid.ee"
    long_poll_timeout: int = 30  # seconds — slightly higher than server's 25s
    long_poll_retry_seconds: int = 5
    firmware_install_command: str = "/opt/kohvrikapid-agent/bin/install-firmware.sh"
    display_enabled: bool = True
    serial_port: Optional[str] = None  # RS485 serial port for KR-BU/NCU* bridge
    serial_baud: int = 19200

    @classmethod
    def load(cls) -> "AgentConfig":
        if not CONFIG_PATH.exists():
            return cls()
        data = tomllib.loads(CONFIG_PATH.read_text())
        return cls(
            server_url=data.get("server_url", cls.server_url),
            long_poll_timeout=int(data.get("long_poll_timeout", cls.long_poll_timeout)),
            long_poll_retry_seconds=int(data.get("long_poll_retry_seconds", cls.long_poll_retry_seconds)),
            firmware_install_command=data.get("firmware_install_command", cls.firmware_install_command),
            display_enabled=bool(data.get("display_enabled", cls.display_enabled)),
            serial_port=data.get("serial_port"),
            serial_baud=int(data.get("serial_baud", cls.serial_baud)),
        )


@dataclass
class AgentSecrets:
    """Salvestatud serveri-pool teostatud registratsiooni info."""
    device_id: Optional[str] = None
    agent_token: Optional[str] = None
    serial: Optional[str] = None

    @classmethod
    def load(cls) -> "AgentSecrets":
        if not SECRETS_PATH.exists():
            return cls()
        data = tomllib.loads(SECRETS_PATH.read_text())
        return cls(
            device_id=data.get("device_id"),
            agent_token=data.get("agent_token"),
            serial=data.get("serial"),
        )

    def save(self) -> None:
        SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {}
        if self.device_id:
            payload["device_id"] = self.device_id
        if self.agent_token:
            payload["agent_token"] = self.agent_token
        if self.serial:
            payload["serial"] = self.serial
        SECRETS_PATH.write_bytes(tomli_w.dumps(payload).encode())
        os.chmod(SECRETS_PATH, 0o600)


def read_or_create_serial() -> str:
    """Stabiilne seerianumber — esimesel käivitusel genereeritakse, salvestatakse failina."""
    if SERIAL_PATH.exists():
        return SERIAL_PATH.read_text().strip()
    # Try Pi CPU serial first
    serial = _read_cpu_serial()
    if not serial:
        import uuid
        serial = "PI-" + uuid.uuid4().hex[:12].upper()
    SERIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERIAL_PATH.write_text(serial)
    os.chmod(SERIAL_PATH, 0o644)
    return serial


def _read_cpu_serial() -> Optional[str]:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    val = line.split(":", 1)[1].strip()
                    if val and val != "0000000000000000":
                        return f"PI-{val[-12:].upper()}"
    except FileNotFoundError:
        return None
    return None
