"""HTTP klient platformi suunal — outbound-only."""
from __future__ import annotations
import logging
from typing import Any, Optional

import httpx

from . import __version__

log = logging.getLogger(__name__)


class AgentClient:
    def __init__(self, server_url: str, device_id: Optional[str] = None, agent_token: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.agent_token = agent_token
        self._http = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=40.0, write=10.0, pool=5.0),
            headers={"User-Agent": f"kohvrikapid-agent/{__version__}"},
            follow_redirects=False,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AgentClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _agent_headers(self) -> dict[str, str]:
        if not self.device_id or not self.agent_token:
            raise RuntimeError("Agent not registered — call register() first")
        return {
            "X-Device-Id": self.device_id,
            "Authorization": f"Bearer {self.agent_token}",
        }

    def register(self, serial: str, hardware_kind: str, hardware_info: dict, agent_version: str, firmware_version: str | None) -> dict:
        body = {
            "serial": serial,
            "hardware_kind": hardware_kind,
            "hardware_info": hardware_info,
            "agent_version": agent_version,
            "firmware_version": firmware_version,
        }
        r = self._http.post(f"{self.server_url}/api/agent/v1/register", json=body)
        r.raise_for_status()
        data = r.json()
        self.device_id = data["device_id"]
        self.agent_token = data["agent_token"]
        return data

    def long_poll(self, *, agent_version: str, firmware_version: str | None, hardware_info: dict, extra: dict | None) -> dict:
        body: dict[str, Any] = {
            "agent_version": agent_version,
            "firmware_version": firmware_version,
            "hardware_info": hardware_info,
        }
        if extra is not None:
            body["extra"] = extra
        r = self._http.post(
            f"{self.server_url}/api/agent/v1/long-poll",
            json=body,
            headers=self._agent_headers(),
            timeout=httpx.Timeout(connect=10.0, read=35.0, write=10.0, pool=5.0),
        )
        r.raise_for_status()
        return r.json()

    def post_solar_reading(self, values: dict) -> None:
        """Saadab ühe MPPT live-lugemi serverisse (aegrida = ajalugu).
        `values` = parse_frame() väljund (ts, raw_hex + mõõteväljad)."""
        r = self._http.post(
            f"{self.server_url}/api/agent/v1/solar/reading",
            json=values,
            headers=self._agent_headers(),
        )
        r.raise_for_status()

    def post_solar_scan_result(self, candidates: list[dict]) -> None:
        """Saadab BLE-skanni tulemuse (kandidaatseadmed) serverisse."""
        r = self._http.post(
            f"{self.server_url}/api/agent/v1/solar/scan-result",
            json={"candidates": candidates},
            headers=self._agent_headers(),
        )
        r.raise_for_status()

    def ack_command(self, command_id: str, *, status: str, result: dict | None) -> None:
        r = self._http.post(
            f"{self.server_url}/api/agent/v1/commands/{command_id}/ack",
            json={"status": status, "result": result},
            headers=self._agent_headers(),
        )
        r.raise_for_status()

    def download_firmware(self, firmware_id: str, dest_path: str) -> None:
        with self._http.stream(
            "GET",
            f"{self.server_url}/api/agent/v1/firmware/{firmware_id}/download",
            headers=self._agent_headers(),
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0),
        ) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as out:
                for chunk in r.iter_bytes(1024 * 1024):
                    out.write(chunk)

    def firmware_applied(self, firmware_id: str) -> None:
        r = self._http.post(
            f"{self.server_url}/api/agent/v1/firmware/{firmware_id}/applied",
            headers=self._agent_headers(),
        )
        r.raise_for_status()
