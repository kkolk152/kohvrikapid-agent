"""Kerong TCP lukukontrolleri + LAN seade discovery.

Pi agent skaneerib aktiivset alamvõrku (vt :mod:`network.discovery_subnet`)
ja teeb kahe sammuna:

1. ARP-stiilis sweep: ping kõik subneti hostid (väikse timeout-iga), siis
   loeb `/proc/net/arp` ja saab MAC-aadressid.
2. Iga elava MAC-i jaoks TCP-probe Kerong-portidele (4001, 4196) + 80/443/8080
   (web bridges) + 23 (telnet). Tagastab vendor OUI hint-i ja avatud portide
   listi.

Tulemused raporteeritakse platformile long-poll extra-s — admin näeb UI-st
kõik subneti seadmed ja saab kinnitada, milline on kontroller.

Cache TTL 5 min, et long-poll-i mitte koormata.
"""
from __future__ import annotations
import concurrent.futures
import ipaddress
import logging
import re
import socket
import subprocess
import time
from typing import Optional

from . import network

log = logging.getLogger(__name__)

KERONG_PORTS = (4001, 4196)  # ZNE-100TL+ kasutab 4196, vanemad mudelid 4001
WEB_PORTS = (80, 8080, 443)
TELNET_PORT = 23
CONNECT_TIMEOUT = 0.3
SCAN_WORKERS = 32
PING_WORKERS = 64
CACHE_TTL_SECONDS = 300

# OUI prefiksid (esimesed 3 baiti MAC-st) — kontrolleri tootjate fingerprint.
# Kerong ametlikku OUI-d ei avalda; ZNE-100TL+ on tegelikult Hi-Flying (HF-LPB100).
# IOT lülitite tüüpilised OUI-d:
KNOWN_OUIS: dict[str, str] = {
    "f0:fe:6b": "Hi-Flying/ZNE-100TL+",
    "d8:b0:4c": "Hi-Flying",
    "5c:cf:7f": "Espressif (ESP8266/ESP32)",
    "84:f3:eb": "Espressif",
    "c8:c9:a3": "Espressif",
    "30:ae:a4": "Espressif",
    "00:11:5b": "Kerong (LCD)",
    "00:1e:c0": "Microchip (RS485 bridges)",
}

_cache: dict = {"ts": 0.0, "subnet": None, "hits": [], "neighbors": []}


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
    # Probe iga host iga teadaoleva pordi suhtes (4001 vanad, 4196 ZNE-100TL+)
    with concurrent.futures.ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        futures = {}
        for ip in hosts:
            for port in KERONG_PORTS:
                futures[ex.submit(_check_port, ip, port)] = (ip, port)
        for fut in concurrent.futures.as_completed(futures):
            ip, port = futures[fut]
            try:
                if fut.result():
                    hits.append({"ip": ip, "port": port, "scanned_at": time.time()})
            except Exception as e:
                log.debug("Skaneerimise viga %s:%s: %s", ip, port, e)

    _cache.update({"ts": now, "subnet": subnet_cidr, "hits": hits})
    log.info("Kerong discovery valmis — leitud %d hosti", len(hits))
    return hits


def _check_port(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _ping(ip: str) -> bool:
    """ICMP ping (1 paketti, 0.5s timeout). Tühistab kogu süsteemi ARP-tabeli ehitust."""
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "1", "-q", ip],
            capture_output=True, timeout=2,
        )
        return r.returncode == 0
    except Exception:
        return False


def _read_arp_table() -> dict[str, str]:
    """Tagasta {ip: mac} kõigi /proc/net/arp kirjete kohta (välja arvatud 00:00:00:00:00:00)."""
    out: dict[str, str] = {}
    try:
        with open("/proc/net/arp") as f:
            next(f, None)  # header
            for line in f:
                parts = line.split()
                if len(parts) < 4:
                    continue
                ip, _, _, mac, _, _ = parts[:6] if len(parts) >= 6 else (parts + [""] * (6 - len(parts)))
                if mac and mac != "00:00:00:00:00:00":
                    out[ip] = mac.lower()
    except Exception as e:
        log.debug("ARP read failed: %s", e)
    return out


def _oui_hint(mac: str) -> Optional[str]:
    if not mac:
        return None
    prefix = mac.lower()[:8]
    return KNOWN_OUIS.get(prefix)


def scan_neighbors(subnet_cidr: Optional[str] = None, force: bool = False) -> list[dict]:
    """Lai LAN-skanner: pingib subneti, loeb ARP-tabeli, probe-b iga MAC-i TCP-portid.

    Tagastab listi: ``{"ip", "mac", "oui_hint", "ports": [4001, 80, ...]}``.
    """
    subnet_cidr = subnet_cidr or network.discovery_subnet()
    if not subnet_cidr:
        return []
    now = time.time()
    if (
        not force
        and _cache["subnet"] == subnet_cidr
        and now - _cache["ts"] < CACHE_TTL_SECONDS
        and _cache["neighbors"]
    ):
        return list(_cache["neighbors"])

    try:
        net = ipaddress.IPv4Network(subnet_cidr, strict=False)
    except ValueError:
        return []
    if net.num_addresses > 1024:
        log.warning("Subnet %s liiga suur (%d) — skip neighbors scan", subnet_cidr, net.num_addresses)
        return []

    hosts = [str(ip) for ip in net.hosts()]
    log.info("LAN neighbors scan — subnet=%s hosts=%d", subnet_cidr, len(hosts))

    # 1) ping kõik (ARP-tabel täidetakse Linux-kerneli poolt automaatselt)
    with concurrent.futures.ThreadPoolExecutor(max_workers=PING_WORKERS) as ex:
        list(ex.map(_ping, hosts))

    arp = _read_arp_table()
    log.info("ARP: %d MACs found", len(arp))

    # 2) TCP-probe iga elava MAC-i jaoks
    probe_ports = KERONG_PORTS + WEB_PORTS + (TELNET_PORT,)
    neighbors: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        port_futures: dict = {}
        for ip in arp.keys():
            for p in probe_ports:
                port_futures[ex.submit(_check_port, ip, p)] = (ip, p)
        ports_by_ip: dict[str, list[int]] = {}
        for fut in concurrent.futures.as_completed(port_futures):
            ip, p = port_futures[fut]
            try:
                if fut.result():
                    ports_by_ip.setdefault(ip, []).append(p)
            except Exception:
                pass

    for ip, mac in arp.items():
        ports = sorted(ports_by_ip.get(ip, []))
        is_kerong = any(p in KERONG_PORTS for p in ports)
        neighbors.append({
            "ip": ip,
            "mac": mac,
            "oui_hint": _oui_hint(mac),
            "ports": ports,
            "looks_like_controller": is_kerong or _oui_hint(mac) is not None,
        })

    # Salvesta cache-i ka legacy hits jaoks (ainult Kerong portidega seadmed)
    legacy_hits = [
        {"ip": n["ip"], "port": p, "scanned_at": now}
        for n in neighbors for p in n["ports"] if p in KERONG_PORTS
    ]
    _cache.update({
        "ts": now, "subnet": subnet_cidr,
        "hits": legacy_hits, "neighbors": neighbors,
    })
    log.info("LAN scan complete — %d neighbors, %d kerong candidates", len(neighbors), len(legacy_hits))
    return neighbors


def gather_discovery_state(subnet_cidr: Optional[str] = None) -> dict:
    """Telemeetria long-poll-i `extra.discovery` jaoks.

    Tagastatakse cache'itud tulemus (ei käivita uut scani). Sünchroonse
    värskenduse jaoks vt :func:`scan_kerong` ja :func:`scan_neighbors`.
    """
    subnet_cidr = subnet_cidr or network.discovery_subnet()
    if not subnet_cidr:
        return {"subnet": None, "candidates": [], "neighbors": []}
    if _cache["subnet"] != subnet_cidr:
        return {"subnet": subnet_cidr, "candidates": [], "neighbors": [], "stale": True}
    return {
        "subnet": subnet_cidr,
        "candidates": list(_cache["hits"]),
        "neighbors": list(_cache["neighbors"]),
        "scanned_at": _cache["ts"] or None,
    }
