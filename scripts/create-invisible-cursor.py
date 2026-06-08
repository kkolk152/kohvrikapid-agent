#!/usr/bin/env python3
"""Loo binaarne XCursor teema "invisible" — 1x1 transparent piksel.

XCursor format spec: https://www.freedesktop.org/wiki/Specifications/cursor-spec/

Tagajärg: wlroots (cage) leiab XCURSOR_PATH+XCURSOR_THEME kaudu selle teema,
võtab cursor-i kui "default", aga renderdab nullide alpha-ga → hiir nähtamatu.
"""
import os
import struct
from pathlib import Path

THEME_DIR = Path("/var/lib/kohvrikapid-agent/cursors/invisible/cursors")
THEME_DIR.mkdir(parents=True, exist_ok=True)

# index.theme — XCursor teemast tähisus
theme_index = Path("/var/lib/kohvrikapid-agent/cursors/invisible/index.theme")
theme_index.write_text("[Icon Theme]\nName=Invisible\nInherits=\n")

# Binaarne 1x1 transparent kursor
def build_cursor() -> bytes:
    magic = b"Xcur"
    header_size = 16
    version = 0x10000
    ntoc = 1
    # Image header on file offset = 16 (peater) + 12 (TOC) = 28
    image_offset = 28
    image_type = 0xfffd0002
    subtype = 1  # size hint = 1 px

    out = magic
    out += struct.pack("<I", header_size)
    out += struct.pack("<I", version)
    out += struct.pack("<I", ntoc)
    # TOC entry (12 bytes)
    out += struct.pack("<III", image_type, subtype, image_offset)
    # Image header (36 bytes)
    out += struct.pack(
        "<IIIIIIIII",
        36,           # header_size
        image_type,   # type
        subtype,      # subtype = size
        1,            # version
        1,            # width
        1,            # height
        0,            # xhot
        0,            # yhot
        0,            # delay
    )
    # 1 transparent BGRA pixel
    out += b"\x00\x00\x00\x00"
    return out

cursor_bytes = build_cursor()

# Salvesta kõige tavaliste cursor nimedega — wlroots/Chromium võivad küsida erinevaid
for name in [
    "default", "left_ptr", "arrow", "pointer", "hand2", "hand1",
    "xterm", "text", "wait", "watch", "crosshair", "move", "fleur",
    "context-menu", "help", "progress", "not-allowed", "grab", "grabbing",
    "n-resize", "s-resize", "e-resize", "w-resize",
    "ne-resize", "nw-resize", "se-resize", "sw-resize",
]:
    (THEME_DIR / name).write_bytes(cursor_bytes)

# Maksta lugemisõigus kõigile
os.system(f"chmod -R a+r /var/lib/kohvrikapid-agent/cursors")

print(f"Created invisible cursor theme at {THEME_DIR}")
