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
        if self.path == "/api/tenant-ready":
            # Vastab 200-ga AINULT kui state-is on tenant config kohal (kapi
            # boot-race vältimiseks: chromium ei tohi laadida JS-i enne kui
            # contact_phone/contact_email/tenant_name on long-pollist tulnud).
            state = self._load_state()
            view = state.get("view")
            phone = state.get("contact_phone")
            tenant = state.get("tenant_name")
            ready = bool(
                view == "READY"
                and isinstance(phone, str) and phone
                and isinstance(tenant, str) and tenant
            )
            self._send_json(
                {"ready": ready, "view": view, "has_phone": bool(phone), "has_tenant": bool(tenant)},
                status=200 if ready else 503,
            )
            return
        if self.path == "/maintenance":
            self._send_json({"enabled": False})
            return
        if self.path == "/TH-Express-202604.png":
            if self._serve_tenant_logo():
                return
        # Patch JS bundle: asenda hardcoded Tallink phone/email/brand/lockers
        # tenant brand-ist tulnud väärtustega
        if self.path.startswith("/assets/") and self.path.endswith(".js"):
            if self._serve_patched_js():
                return
        # Static fallback (SPA): kui faili pole, serveeri index.html
        full = self._dist_dir / self.path.lstrip("/").split("?", 1)[0]
        if self.path != "/" and not full.exists():
            self.path = "/"
        super().do_GET()

    def _serve_patched_js(self) -> bool:
        rel = self.path.lstrip("/").split("?", 1)[0]
        full = self._dist_dir / rel
        if not full.exists():
            return False
        state = self._load_state()
        try:
            content = full.read_text()
        except Exception:
            return False

        # 1) telefon
        phone = state.get("contact_phone")
        if isinstance(phone, str) and phone:
            content = content.replace('"6678700"', f'"{phone}"')
        # 2) email — kõikjal, sh mailto:
        email = state.get("contact_email")
        if isinstance(email, str) and email:
            content = content.replace('"expresshotel@tallink.ee"', f'"{email}"')
            content = content.replace('"mailto:expresshotel@tallink.ee"', f'"mailto:{email}"')
        # 3) brand nimi
        brand = state.get("tenant_name") or state.get("cabinet_name")
        if isinstance(brand, str) and brand:
            content = content.replace('"TH Express"', f'"{brand}"')
            content = content.replace('"Tallink Express"', f'"{brand}"')
            content = content.replace('"Tallink Tarmo"', f'"{brand}"')
        # 4) kapi loend mp=[...] -> uue suuruse järgi N kappi
        slot_count = state.get("slot_count")
        if isinstance(slot_count, int) and slot_count > 0:
            content = self._patch_locker_array(content, slot_count)

        # 5) Reference Pi UI helistab localhost:9122 (NCU48L locker-control), :9131
        # (kiosk-sms-center) jne. Need meil pole — suuname kõik kioski same-origin-i
        # peale, kus me proxime relevant endpoint-id platformi-le.
        content = content.replace('"http://127.0.0.1:9122"', '""')
        content = content.replace('"http://127.0.0.1:9131"', '""')

        # 6) Hinnastus + makse: tasuta režiim ja per-cabinet hinnatabel
        payment = state.get("payment") or {}
        pricing = state.get("pricing") or {}
        tiers = pricing.get("tiers") if isinstance(pricing, dict) else None
        if isinstance(tiers, list) and tiers:
            # SIZE_PRICES tabeli asendus. Reference: const SIZE_PRICES={S:{6:3,24:6},M:...}
            # Minified bundle-is on selliselt: {S:{6:3,24:6},M:{6:3,24:6},L:{6:4,24:8},XL:{6:5,24:10}}
            # Genereeri identne struktuur uute tier-ide järgi (sama hind kõikidele sizes).
            def _mk(size_mult: float) -> str:
                inner = ",".join(
                    f"{int(t.get('hours', 0))}:{round(float(t.get('price', 0)) * size_mult, 2)}"
                    for t in tiers if isinstance(t, dict)
                )
                return "{" + inner + "}"
            old_table = "{S:{6:3,24:6},M:{6:3,24:6},L:{6:4,24:8},XL:{6:5,24:10}}"
            new_table = "{S:" + _mk(1.0) + ",M:" + _mk(1.0) + ",L:" + _mk(1.3) + ",XL:" + _mk(1.7) + "}"
            content = content.replace(old_table, new_table)

        # 7) Free mode: kui makset pole, surume DurationPage onPay otse PinCreate-le.
        # Praegu jätame UI muutmata — bundle PaymentPage'i refaktoreerimine on too
        # invasive. Asemel: backend ignoreerib paid_amount free_mode case-is.

        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True

    @staticmethod
    def _patch_locker_array(js: str, n: int) -> str:
        """Asenda `mp=[{id:"locker-1",...},...]` uue N kapiga."""
        anchor = '[{id:"locker-1",number:"01"'
        start = js.find(anchor)
        if start < 0:
            return js
        depth = 0
        end = -1
        for i in range(start, min(start + 200_000, len(js))):
            ch = js[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            return js
        items = []
        for i in range(1, n + 1):
            items.append(
                f'{{id:"locker-{i}",number:"{i:02d}",size:"M",cu:"CU1",lock:{i}}}'
            )
        new_arr = "[" + ",".join(items) + "]"
        return js[:start] + new_arr + js[end:]

    def _serve_tenant_logo(self) -> bool:
        """Kui display_state-is on tenant logo, serveeri see; muidu False -> default."""
        state = self._load_state()
        # logo_data_uri prioriteet (base64 PNG) — sõltumatu võrgust
        data_uri = state.get("logo_data_uri")
        if isinstance(data_uri, str) and data_uri.startswith("data:image/"):
            try:
                import base64
                head, b64 = data_uri.split(",", 1)
                mime = head.split(";", 1)[0].replace("data:", "")
                body = base64.b64decode(b64)
                self.send_response(200)
                self.send_header("Content-Type", mime or "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=60")
                self.end_headers()
                self.wfile.write(body)
                return True
            except Exception as e:
                log.warning("logo_data_uri decode failed: %s", e)
        # logo_url — proxy fetch
        logo_url = state.get("logo_url")
        if isinstance(logo_url, str) and logo_url.startswith(("http://", "https://")):
            try:
                r = httpx.get(logo_url, timeout=5)
                if r.status_code == 200:
                    ct = r.headers.get("Content-Type", "image/png")
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(r.content)))
                    self.send_header("Cache-Control", "max-age=60")
                    self.end_headers()
                    self.wfile.write(r.content)
                    return True
                log.warning("logo fetch %s: HTTP %d", logo_url, r.status_code)
            except Exception as e:
                log.warning("logo fetch %s failed: %s", logo_url, e)
        return False

    def _load_state(self) -> dict:
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
        return {}

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/storage/verify-pin":
            self._proxy_storage_verify_pin()
            return
        if self.path == "/api/storage/start":
            self._proxy_storage_start()
            return
        # Reference Pi locker-control shim endpoints — JS bundle helistab nendele
        # samm-sammult avamise voos. Kõik lähevad lihtsalt 200/ok, kuni reaalne
        # avamine toimub backend-i poolt (open_slot command long-polli kaudu).
        if self.path in ("/open", "/sessions", "/sessions/close", "/probe"):
            self._send_json({"ok": True, "note": "platform-side open"})
            return
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"not_found"}')

    def _proxy_storage_start(self) -> None:
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
        url = f"{config.server_url.rstrip('/')}/api/agent/v1/storage/start"
        headers = {
            "X-Device-Id": secrets.device_id,
            "Authorization": f"Bearer {secrets.agent_token}",
            "Content-Type": "application/json",
        }
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=15)
            self._send_json(r.json(), status=r.status_code)
        except Exception as e:
            log.error("storage/start proxy ebaõnnestus: %s", e)
            self._send_json({"ok": False, "error": f"network: {e}"}, status=502)

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
