"""Draws the kind icons into workflow/icons; rerun after changing a colour."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 128
SAMPLES = 4
RADIUS = 0.34
RING = 0.11

OCHRE = (0xC8, 0x90, 0x2A)
GREEN = (0x5B, 0x9A, 0x6A)
TERRACOTTA = (0xC2, 0x50, 0x3D)
BLUE = (0x4A, 0x7F, 0xB5)
PLUM = (0x8A, 0x5A, 0x9E)

ICONS = {
    "log": (GREEN, False),
    "task": (OCHRE, True),
    "done": (OCHRE, False),
    "note": (TERRACOTTA, False),
    "question": (BLUE, True),
    "decision": (BLUE, False),
    "checklist": (PLUM, True),
}


def coverage(x: int, y: int, hollow: bool) -> float:
    inside = 0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            px = (x + (sx + 0.5) / SAMPLES) / SIZE - 0.5
            py = (y + (sy + 0.5) / SAMPLES) / SIZE - 0.5
            distance = (px * px + py * py) ** 0.5
            if distance <= RADIUS and (not hollow or distance >= RADIUS - RING):
                inside += 1
    return inside / (SAMPLES * SAMPLES)


def rows(colour: tuple[int, int, int], hollow: bool) -> bytes:
    out = bytearray()
    for y in range(SIZE):
        out.append(0)
        for x in range(SIZE):
            out.extend(colour)
            out.append(round(255 * coverage(x, y, hollow)))
    return bytes(out)


def chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def png(colour: tuple[int, int, int], hollow: bool) -> bytes:
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows(colour, hollow), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    folder = Path(__file__).parent / "icons"
    folder.mkdir(exist_ok=True)
    for name, (colour, hollow) in ICONS.items():
        (folder / f"{name}.png").write_bytes(png(colour, hollow))


if __name__ == "__main__":
    main()
