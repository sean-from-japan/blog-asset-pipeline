"""Shared fixtures.

Every image used by the tests is generated here from a few bytes of header
data. Nothing binary is committed, and the suite has no image library
dependency.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def write_png(path: Path, width: int, height: int) -> Path:
    """Write the smallest valid PNG with the requested dimensions."""
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    return path


def write_gif(path: Path, width: int, height: int) -> Path:
    path.write_bytes(b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00")
    return path


def write_jpeg(path: Path, width: int, height: int) -> Path:
    """A JPEG whose frame header sits behind a metadata segment."""
    comment = b"\xff\xfe" + struct.pack(">H", 2 + 4) + b"note"
    frame = (
        b"\xff\xc0"
        + struct.pack(">H", 11)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x01\x01\x11\x00"
    )
    path.write_bytes(b"\xff\xd8" + comment + frame + b"\xff\xd9")
    return path


def write_webp(path: Path, width: int, height: int) -> Path:
    payload = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00"
    payload += (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    path.write_bytes(b"RIFF" + struct.pack("<I", len(payload) + 4) + b"WEBP" + payload)
    return path


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def png(tmp_path):
    def make(name: str, width: int, height: int) -> Path:
        return write_png(tmp_path / name, width, height)

    return make
