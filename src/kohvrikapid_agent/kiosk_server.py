"""Lokaalne HTTP server kioski UI jaoks (localhost:7080).

Serveerib Vite + Svelte built dist/ failid + JSON state endpoint-i. Chromium
kiosk Pi peal kuvab http://localhost:7080/.

Vältige täiendavate sõltuvuste lisamist (FastAPI, uvicorn) — kasutame ainult
stdlib `http.server`-it eraldi threadis. Kerge ja sobib kioskile.
"""
from __future__ import annotations
import http.server
import json
import logging
import os
import socketserver
import threading
from pathlib import Path
from typing import Optional

import httpx

from .config import AgentConfig, AgentSecrets

log = logging.getLogger(__name__)

# Pi-l: /opt/kohvrikapid-agent/kiosk/dist/
DIST_DIR_CANDIDATES = [
    Path("/opt/kohvrikapid-agent/kiosk/dist"),
    Path(__file__).resolve().parent.parent.parent / "kiosk" / "dist",
]

STATE_FILE = Path("/var/lib/kohvrikapid-agent/display_state.json")
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 7080


def find_dist_dir() -> Optional[Path]:
    for p in DIST_DIR_CANDIDATES:
        if (p / "index.html").exists():
            return p
    return None


class _Handler(http.server.SimpleHTTPRequestHandler):
    # Set in start_kiosk_server
    _dist_dir: Path = Path("/")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self._dist_dir), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Suuname stdout-i asemel logger-isse, INFO tasemel ainult error-id
        log.debug("kiosk-http %s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/state":
            self._serve_state()
            return
        if self.path == "/api/healthz":
            self._send_json({"ok": True})
            return
        # Static fallback (SPA): kui faili pole, serveeri index.html
        full = self._dist_dir / self.path.lstrip("/").split("?", 1)[0]
        if self.path != "/" and not full.exists():
            self.path = "/"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/storage/verify-pin":
            self._proxy_storage_verify_pin()
            return
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"not_found"}')

    def _proxy_storage_verify_pin(self) -> None:
        """Edasta PIN platformi /api/agent/v1/storage/verify-pin endpoint-ile."""
        length = int(self.headers.get("Content-Length") or 0)
        body_raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(body_raw)
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "bad_json"}, status=400)
            return

        config = AgentConfig.load()
        secrets = AgentSecrets.load()
        if not secrets.device_id or not secrets.agent_token:
            self._send_json({"ok": False, "error": "agent_not_registered"}, status=503)
            return

        url = f"{config.server_url.rstrip('/')}/api/agent/v1/storage/verify-pin"
        headers = {
            "X-Device-Id": secrets.device_id,
            "Authorization": f"Bearer {secrets.agent_token}",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(url, json={"pin": str(body.get("pin", ""))}, headers=headers, timeout=10)
            data = r.json()
            log.info("storage verify-pin -> %s (status=%d)", data.get("ok"), r.status_code)
            self._send_json(data, status=r.status_code)
        except Exception as e:
            log.error("storage verify-pin proxy ebaõnnestus: %s", e)
            self._send_json({"ok": False, "error": f"network: {e}"}, status=502)

    def _serve_state(self) -> None:
        state: dict = {"view": "BOOTING"}
        try:
            if STATE_FILE.exists():
                state = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.debug("State faili lugemine ebaõnnestus: %s", e)
        self._send_json(state)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_server_thread: Optional[threading.Thread] = None
_server: Optional[_Server] = None


def start_kiosk_server() -> bool:
    """Käivita HTTP server taustathreadis. Tagastab True kui käivitus õnnestus."""
    global _server_thread, _server
    dist = find_dist_dir()
    if not dist:
        log.warning("kiosk_server: dist/ kataloogi ei leitud — kiosk UI ei tööta")
        return False
    log.info("kiosk_server: serveerin %s -> http://%s:%d", dist, LISTEN_HOST, LISTEN_PORT)

    _Handler._dist_dir = dist
    try:
        _server = _Server((LISTEN_HOST, LISTEN_PORT), _Handler)
    except OSError as e:
        log.error("kiosk_server: port %d kasutuses (%s) — kiosk UI ei käivitu", LISTEN_PORT, e)
        return False

    _server_thread = threading.Thread(target=_server.serve_forever, name="kiosk-server", daemon=True)
    _server_thread.start()
    return True


def stop_kiosk_server() -> None:
    if _server is not None:
        _server.shutdown()
