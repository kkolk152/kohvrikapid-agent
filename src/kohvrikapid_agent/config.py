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
    server_url: str = "https://ctr-locker.kakuweb.ee"
    long_poll_timeout: int = 30  # seconds — slightly higher than server's 25s
    long_poll_retry_seconds: int = 5
    firmware_install_command: str = "/opt/kohvrikapid-agent/bin/install-firmware.sh"
    # "auto" — vaatab /dev/fb0; "force_on" — alati renderda; "force_off" — headless
    display_mode: str = "auto"
    serial_port: Optional[str] = None  # RS485 serial port for KR-BU/NCU* bridge
    serial_baud: int = 19200
    # Discovery skaneerib kuni n hosti — kaitse vea/valesti seadistatud subneti vastu
    discovery_enabled: bool = True
    discovery_interval_minutes: int = 30

    @classmethod
    def load(cls) -> "AgentConfig":
        if not CONFIG_PATH.exists():
            return cls()
        data = tomllib.loads(CONFIG_PATH.read_text())
        # Tagasiühilduvus: vana "display_enabled" → uus "display_mode"
        display_mode = data.get("display_mode")
        if display_mode is None:
            legacy = data.get("display_enabled")
            if legacy is True:
                display_mode = "auto"
            elif legacy is False:
                display_mode = "force_off"
            else:
                display_mode = cls.display_mode
        return cls(
            server_url=data.get("server_url", cls.server_url),
            long_poll_timeout=int(data.get("long_poll_timeout", cls.long_poll_timeout)),
            long_poll_retry_seconds=int(data.get("long_poll_retry_seconds", cls.long_poll_retry_seconds)),
            firmware_install_command=data.get("firmware_install_command", cls.firmware_install_command),
            display_mode=display_mode,
            serial_port=data.get("serial_port"),
            serial_baud=int(data.get("serial_baud", cls.serial_baud)),
            discovery_enabled=bool(data.get("discovery_enabled", cls.discovery_enabled)),
            discovery_interval_minutes=int(data.get("discovery_interval_minutes", cls.discovery_interval_minutes)),
        )

    def resolve_display_enabled(self) -> bool:
        """Lõplik otsus kas ekraani render aktiivne (võtab arvesse auto + /dev/fb0)."""
        if self.display_mode == "force_on":
            return True
        if self.display_mode == "force_off":
            return False
        # auto
        from .display import display_available
        return display_available()


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
