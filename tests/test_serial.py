"""Sanity test — serial number generation."""
import os
import tempfile
from pathlib import Path

import kohvrikapid_agent.config as cfg_module


def test_serial_generation(monkeypatch, tmp_path):
    serial_path = tmp_path / "serial"
    monkeypatch.setattr(cfg_module, "SERIAL_PATH", serial_path)
    monkeypatch.setattr(cfg_module, "_read_cpu_serial", lambda: None)
    s = cfg_module.read_or_create_serial()
    assert s.startswith("PI-")
    assert len(s) >= 10
    # idempotent
    s2 = cfg_module.read_or_create_serial()
    assert s == s2
