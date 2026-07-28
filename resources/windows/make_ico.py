#!/usr/bin/env python3
"""Rebuild the Windows .ico from the per-size PNG icons.

Windows will not reliably render PNG-compressed icon entries below 256x256
out of an executable's resources: Explorer and the task bar expect BMP/DIB
there, and fall back to a generic icon when they find PNG. Pillow writes
every entry as PNG, so the entries are assembled here instead.

The 256x256 entry stays PNG, which is both supported and conventional --
as a BMP it would add roughly 256 KB for no benefit.

Usage:
    python3 resources/windows/make_ico.py
"""

import struct
import sys
from pathlib import Path

from PIL import Image

ICONS = Path(__file__).resolve().parents[2] / 'src/pynetboot/resources/icons'
TARGET = ICONS / 'unetbootin.ico'

# Sizes Windows picks between. Each has its own hand-authored PNG, so they
# are used directly rather than rescaling one source image.
BMP_SIZES = (16, 24, 32, 48, 64, 128)
PNG_SIZE = 256


def dib_entry(image: Image.Image) -> bytes:
    """Encode an image as the BMP/DIB payload of an icon entry."""
    width, height = image.size
    pixels = image.load()

    # 32bpp BGRA, bottom-up.
    xor = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            xor += bytes((b, g, r, a))

    # 1bpp AND mask, bottom-up, each row padded to a 4-byte boundary. The
    # alpha channel already carries transparency, so the mask is all zeros,
    # but Windows still requires it to be present and correctly sized.
    row_bytes = ((width + 31) // 32) * 4
    and_mask = bytes(row_bytes * height)

    header = struct.pack(
        '<IiiHHIIiiII',
        40,                  # header size
        width,
        height * 2,          # XOR and AND masks stacked
        1,                   # planes
        32,                  # bits per pixel
        0,                   # BI_RGB, uncompressed
        len(xor) + len(and_mask),
        0, 0, 0, 0,
    )
    return header + bytes(xor) + and_mask


def build() -> bytes:
    payloads = []

    for size in BMP_SIZES:
        source = ICONS / f'unetbootin_{size}.png'
        if not source.exists():
            sys.exit(f"missing source icon: {source}")
        with Image.open(source) as image:
            payloads.append((size, dib_entry(image.convert('RGBA')), False))

    source = ICONS / f'unetbootin_{PNG_SIZE}.png'
    if not source.exists():
        sys.exit(f"missing source icon: {source}")
    payloads.append((PNG_SIZE, source.read_bytes(), True))

    header = struct.pack('<HHH', 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)

    directory = b''
    for size, payload, _is_png in payloads:
        directory += struct.pack(
            '<BBBBHHII',
            0 if size == 256 else size,   # 0 means 256 in an icon directory
            0 if size == 256 else size,
            0,                            # colours in palette
            0,                            # reserved
            1,                            # planes
            32,                           # bits per pixel
            len(payload),
            offset,
        )
        offset += len(payload)

    return header + directory + b''.join(p for _s, p, _i in payloads)


if __name__ == '__main__':
    TARGET.write_bytes(build())
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes)")
