"""Kerong TCP lukukontrolleri discovery.

Pi agent skaneerib aktiivset alamvõrku (vt :mod:`network.discovery_subnet`)
ja otsib Kerong KR-BU võrgukontrollereid, mis kuulavad pordi 4001 peal
(`KERONG_PORT`). Leitud kandidaadid raporteeritakse platformile long-poll
extra-s — admin saab UI-st valida, kumb kontroller mis kapiga seotud on.

Discovery on **mitte-invasiivne**: ainult TCP SYN/connect, ühtegi käsku ei
saadeta. Tulemused cache'itakse 5 min, et long-poll-i mitte koormata.
"""
from __future__ import annotations
import concurrent.futures
import ipaddress
import logging
import socket
import time
from typing import Optional

from . import network

log = logging.getLogger(__name__)

KERONG_PORT = 4001
CONNECT_TIMEOUT = 0.3  # sekund per host
SCAN_WORKERS = 32
CACHE_TTL_SECONDS = 300

_cache: dict = {"ts": 0.0, "subnet": None, "hits": []}


def scan_kerong(subnet_cidr: Optional[str] = None, force: bool = False) -> list[dict]:
    """Skaneeri CIDR-i Kerong (port 4001) avatud hostide leidmiseks.

    Cache'itakse :data:`CACHE_TTL_SECONDS` sekundiks per subnet. Tagasi
    saadakse list dict-e: ``{"ip": "...", "port": 4001, "scanned_at": ts}``.
    """
    subnet_cidr = subnet_cidr or network.discovery_subnet()
    if not subnet_cidr:
        return []
    now = time.time()
    if (
        not force
        and _cache["subnet"] == subnet_cidr
        and now - _cache["ts"] < CACHE_TTL_SECONDS
    ):
        return list(_cache["hits"])

    try:
        net = ipaddress.IPv4Network(subnet_cidr, strict=False)
    except ValueError:
        log.warning("Vigane CIDR discovery jaoks: %s", subnet_cidr)
        return []
    if net.num_addresses > 1024:
        log.warning("Subnet %s liiga suur (%d aadressi) — skip", subnet_cidr, net.num_addresses)
        return []

    hosts = [str(ip) for ip in net.hosts()]
    hits: list[dict] = []
    log.info("Kerong discovery alustab — subnet=%s hosti-arv=%d", subnet_cidr, len(hosts))
    with concurrent.futures.ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        futures = {ex.submit(_check_port, ip, KERONG_PORT): ip for ip in hosts}
        for fut in concurrent.futures.as_completed(futures):
            ip = futures[fut]
            try:
                if fut.result():
                    hits.append({"ip": ip, "port": KERONG_PORT, "scanned_at": time.time()})
            except Exception as e:
                log.debug("Skaneerimise viga %s: %s", ip, e)

    _cache.update({"ts": now, "subnet": subnet_cidr, "hits": hits})
    log.info("Kerong discovery valmis — leitud %d hosti", len(hits))
    return hits


def _check_port(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def gather_discovery_state(subnet_cidr: Optional[str] = None) -> dict:
    """Telemeetria long-poll-i `extra.discovery` jaoks.

    Tagastatakse cache'itud tulemus (ei käivita uut scani). Sünchroonse
    värskenduse jaoks vt :func:`scan_kerong`.
    """
    subnet_cidr = subnet_cidr or network.discovery_subnet()
    if not subnet_cidr:
        return {"subnet": None, "candidates": []}
    if _cache["subnet"] != subnet_cidr:
        return {"subnet": subnet_cidr, "candidates": [], "stale": True}
    return {
        "subnet": subnet_cidr,
        "candidates": list(_cache["hits"]),
        "scanned_at": _cache["ts"] or None,
    }
