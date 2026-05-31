"""OTA tarkvarauuendus: lae alla → kontrolli sha256 → paigalda."""
from __future__ import annotations
import hashlib
import logging
import os
import subprocess
import tempfile

from .client import AgentClient

log = logging.getLogger(__name__)


def apply_firmware(
    client: AgentClient,
    *,
    firmware_id: str,
    sha256_expected: str,
    size_expected: int,
    install_command: str,
) -> bool:
    log.info("OTA: laen alla firmware %s (oodatud %d B)", firmware_id, size_expected)
    fd, path = tempfile.mkstemp(prefix="kohvrikapid-fw-", suffix=".bin")
    os.close(fd)
    try:
        client.download_firmware(firmware_id, path)
    except Exception as e:
        log.error("OTA: download ebaõnnestus: %s", e)
        return False

    actual_size = os.path.getsize(path)
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
    actual_sha = sha.hexdigest()

    if size_expected and actual_size != size_expected:
        log.error("OTA: faili suurus erineb: %d != %d (oodatud)", actual_size, size_expected)
        os.unlink(path)
        return False
    if sha256_expected and actual_sha != sha256_expected:
        log.error("OTA: sha256 ei klapi: %s != %s (oodatud)", actual_sha, sha256_expected)
        os.unlink(path)
        return False

    log.info("OTA: kontrollsumma ok, käivitan paigaldaja: %s %s", install_command, path)
    try:
        result = subprocess.run([install_command, path], timeout=300, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        log.error("OTA: paigaldus aegus")
        os.unlink(path)
        return False
    if result.returncode != 0:
        log.error("OTA: paigaldus tagastas %d: %s", result.returncode, result.stderr)
        os.unlink(path)
        return False
    log.info("OTA: paigaldatud")
    try:
        client.firmware_applied(firmware_id)
    except Exception as e:
        log.warning("OTA: applied-ack saatmine ebaõnnestus: %s", e)
    try:
        os.unlink(path)
    except OSError:
        pass
    return True
