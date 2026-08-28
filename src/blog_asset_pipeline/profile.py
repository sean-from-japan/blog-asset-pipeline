"""Delivery profile: the shape of one delivery package.

Every constraint that differs between clients or content management systems
lives here, so the rest of the pipeline stays free of hard-coded sizes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProfileError(ValueError):
    """Raised when a profile file cannot be turned into a DeliveryProfile."""


@dataclass(frozen=True)
class Size:
    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"

    @classmethod
    def parse(cls, text: str) -> Size:
        normalised = text.strip().lower().replace("×", "x")
        try:
            width, height = normalised.split("x", 1)
            return cls(int(width), int(height))
        except ValueError as exc:  # pragma: no cover - message is the value
            raise ProfileError(f"not a size: {text!r}") from exc


@dataclass(frozen=True)
class DeliveryProfile:
    """Sizes and naming rules a delivery package must satisfy."""

    name: str = "default"
    header: Size = field(default=Size(1600, 1200))
    body: Size = field(default=Size(1200, 900))
    square: Size = field(default=Size(1080, 1080))

    # Content management systems truncate or reject long names, and the limit
    # is counted in bytes, so a non-ASCII title exhausts it far sooner than
    # its character count suggests.
    max_filename_bytes: int = 40

    # Slug length is counted in characters: it only feeds the filename, which
    # is checked against max_filename_bytes separately.
    max_slug_chars: int = 50

    #: Headings shorter than this are reported for review, not rejected.
    min_body_chars: int = 30

    #: Extensions treated as delivery images when looking for stray files.
    image_suffixes: tuple = (".png", ".jpg", ".jpeg", ".webp", ".gif")

    file_suffix: str = ".png"

    def size_for(self, role: str) -> Size:
        try:
            return {"header": self.header, "body": self.body, "square": self.square}[role]
        except KeyError as exc:
            raise ProfileError(f"unknown role: {role!r}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "header": str(self.header),
            "body": str(self.body),
            "square": str(self.square),
            "max_filename_bytes": self.max_filename_bytes,
            "max_slug_chars": self.max_slug_chars,
            "min_body_chars": self.min_body_chars,
            "file_suffix": self.file_suffix,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> DeliveryProfile:
        defaults = cls()
        unknown = set(data) - {
            "name",
            "header",
            "body",
            "square",
            "max_filename_bytes",
            "max_slug_chars",
            "min_body_chars",
            "file_suffix",
        }
        if unknown:
            raise ProfileError(f"unknown profile keys: {sorted(unknown)}")
        return cls(
            name=str(data.get("name", defaults.name)),
            header=Size.parse(data["header"]) if "header" in data else defaults.header,
            body=Size.parse(data["body"]) if "body" in data else defaults.body,
            square=Size.parse(data["square"]) if "square" in data else defaults.square,
            max_filename_bytes=int(data.get("max_filename_bytes", defaults.max_filename_bytes)),
            max_slug_chars=int(data.get("max_slug_chars", defaults.max_slug_chars)),
            min_body_chars=int(data.get("min_body_chars", defaults.min_body_chars)),
            file_suffix=str(data.get("file_suffix", defaults.file_suffix)),
        )

    @classmethod
    def load(cls, path: Path) -> DeliveryProfile:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path}: invalid JSON ({exc})") from exc
        if not isinstance(raw, dict):
            raise ProfileError(f"{path}: expected a JSON object")
        return cls.from_mapping(raw)


DEFAULT_PROFILE = DeliveryProfile()
