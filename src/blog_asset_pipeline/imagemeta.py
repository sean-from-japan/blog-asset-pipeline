"""Read image dimensions from file headers, using the standard library only.

The first version of this workflow shelled out to the macOS ``sips`` command.
That tied the check to one operating system and made it unusable in CI, so
the four container formats a delivery can contain are parsed directly. Only
the header is read, so the cost does not grow with the image.
"""

from __future__ import annotations

import struct
from pathlib import Path


class ImageFormatError(ValueError):
    """Raised when a file is not a supported image or its header is damaged."""


def _png_size(head: bytes) -> tuple[int, int]:
    # 8-byte signature, then a 4-byte length, "IHDR", width, height.
    if len(head) < 24 or head[12:16] != b"IHDR":
        raise ImageFormatError("truncated PNG header")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def _gif_size(head: bytes) -> tuple[int, int]:
    if len(head) < 10:
        raise ImageFormatError("truncated GIF header")
    width, height = struct.unpack("<HH", head[6:10])
    return width, height


def _webp_size(head: bytes) -> tuple[int, int]:
    # Three sub-formats share the RIFF/WEBP container.
    if len(head) < 30:
        raise ImageFormatError("truncated WebP header")
    chunk = head[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(head[24:27], "little") + 1
        height = int.from_bytes(head[27:30], "little") + 1
        return width, height
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", head[26:30])
        return width & 0x3FFF, height & 0x3FFF
    raise ImageFormatError("unsupported WebP sub-format")


def _jpeg_size(path: Path) -> tuple[int, int]:
    # JPEG dimensions live in a start-of-frame marker whose position depends
    # on how many metadata segments precede it, so the segments are walked.
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            raise ImageFormatError("not a JPEG")
        while True:
            marker = handle.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                raise ImageFormatError("damaged JPEG segment table")
            kind = marker[1]
            if kind in (0x01, 0xD8, 0xD9) or 0xD0 <= kind <= 0xD7:
                # Standalone markers carry no length field.
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) < 2:
                raise ImageFormatError("truncated JPEG segment")
            length = struct.unpack(">H", length_bytes)[0]
            # SOF0-SOF15, excluding the four markers that are not frame headers.
            if 0xC0 <= kind <= 0xCF and kind not in (0xC4, 0xC8, 0xCC):
                payload = handle.read(5)
                if len(payload) < 5:
                    raise ImageFormatError("truncated JPEG frame header")
                height, width = struct.unpack(">HH", payload[1:5])
                return width, height
            handle.seek(length - 2, 1)


def image_size(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` in pixels.

    Raises :class:`ImageFormatError` for an unreadable or unsupported file.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(30)
    except OSError as exc:
        raise ImageFormatError(f"cannot read {path.name}: {exc}") from exc
    if not head:
        raise ImageFormatError(f"{path.name} is empty")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_size(head)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return _gif_size(head)
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return _webp_size(head)
    if head.startswith(b"\xff\xd8"):
        return _jpeg_size(path)
    raise ImageFormatError(f"{path.name} is not a PNG, JPEG, GIF or WebP file")


def try_image_size(path: Path) -> tuple[tuple[int, int] | None, str | None]:
    """Non-raising variant: ``(size, None)`` or ``(None, reason)``."""
    try:
        return image_size(path), None
    except ImageFormatError as exc:
        return None, str(exc)
