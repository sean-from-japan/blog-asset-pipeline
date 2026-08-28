"""Filename rules for delivery packages.

Two rules cause most of the rework in a real delivery:

* the target CMS counts filename length in *bytes*, so a heading in a
  non-Latin script overruns a 40-byte budget after roughly 13 characters;
* macOS stores filenames in NFD while editors and ledgers write NFC, so a
  byte-for-byte comparison reports files as missing when they are present.

Both are handled here rather than at every call site.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

#: Characters that are illegal or hostile in a filename on at least one of
#: Windows, macOS and Linux.
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_TRAILING_PUNCTUATION = " .,;:!?-_、。・！？"

#: Punctuation that is legal in a filename but noisy once it reaches a URL.
_FILENAME_NOISE = re.compile(r"[,;:!?'\"()\[\]{}。、・！？「」『』]")


def nfc(text: str) -> str:
    """Normalise to NFC so ledger text and directory entries compare equal."""
    return unicodedata.normalize("NFC", text)


def sanitize(name: str) -> str:
    """Strip characters that cannot appear in a filename."""
    cleaned = _ILLEGAL.sub("", nfc(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.rstrip(_TRAILING_PUNCTUATION)


def byte_limited(name: str, max_bytes: int, fallback: str = "image") -> str:
    """Trim ``name`` to at most ``max_bytes`` UTF-8 bytes without splitting a
    character."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    out = []
    used = 0
    for char in sanitize(name):
        width = len(char.encode("utf-8"))
        if used + width > max_bytes:
            break
        out.append(char)
        used += width
    trimmed = "".join(out).rstrip(_TRAILING_PUNCTUATION)
    return trimmed or fallback


def char_limited(name: str, max_chars: int, fallback: str = "image") -> str:
    """Trim ``name`` to at most ``max_chars`` characters."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    trimmed = sanitize(name)[:max_chars].rstrip(_TRAILING_PUNCTUATION)
    return trimmed or fallback


def filename_stem(text: str, max_bytes: int, fallback: str = "image") -> str:
    """Build the readable part of a filename.

    Spaces are replaced with hyphens: the delivered files end up in URLs, and
    a percent-encoded space makes a link unreadable in a CMS media library.
    """
    without_punctuation = _FILENAME_NOISE.sub(" ", sanitize(text))
    collapsed = re.sub(r"[-\s_]+", "-", without_punctuation).strip("-")
    return byte_limited(collapsed, max_bytes, fallback).strip("-") or fallback


def numbered(index: int, stem: str, suffix: str) -> str:
    """Build the delivery filename: a zero-padded position, then the stem.

    The number is what makes an out-of-order upload obvious in a file
    listing, so it is part of the name rather than only of the ledger.
    """
    if index < 1:
        raise ValueError("index is 1-based")
    return f"{index:02d}_{stem}{suffix}"


def deduplicate(names: Iterable[str]) -> list[str]:
    """Return the names in order, appending ``_2``, ``_3``, ... to repeats.

    Two headings with the same text are common (``Summary`` in a series) and
    must not silently overwrite each other's image.
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        result.append(name if count == 1 else f"{name}_{count}")
    return result


def filename_bytes(name: str) -> int:
    """UTF-8 byte length of a filename, as the CMS counts it."""
    return len(nfc(name).encode("utf-8"))
