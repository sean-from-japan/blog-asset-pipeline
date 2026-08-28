"""The ledger: a Markdown table that is both the checklist and the contract.

A Markdown table is used rather than JSON because the person filling in the
progress columns edits it by hand while working. The parser is therefore
written to survive hand editing: it locates the table by its header row and
matches columns by name, so inserting a column or reordering does not break
the check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .plan import DeliveryPlan

PROGRESS_COLUMNS = ("Generated", "Reviewed", "Alt")
DONE = "yes"
PENDING = "no"

_COLUMNS = (
    "#",
    "Role",
    "Level",
    "Heading",
    "Line",
    "Anchor",
    "Filename",
    "Size",
    "Generated",
    "Reviewed",
    "Alt",
    "Notes",
)

_SEPARATOR = re.compile(r"^[\s|:-]+$")


class LedgerError(ValueError):
    """Raised when a ledger file cannot be parsed into rows."""


@dataclass
class LedgerRow:
    position: int
    role: str
    filename: str
    size: str
    heading: str
    progress: dict[str, str]

    def pending(self) -> list[str]:
        return [name for name in PROGRESS_COLUMNS if self.progress.get(name, PENDING) != DONE]


def _cell(value: str) -> str:
    """Escape a value so it cannot break the table it sits in."""
    return value.replace("|", "\\|").replace("\n", " ").strip() or "-"


def render(plan: DeliveryPlan) -> str:
    lines = [
        f"# Image ledger — {plan.article}",
        "",
        f"Profile: `{plan.profile.name}` · "
        f"header {plan.profile.header} · body {plan.profile.body} · square {plan.profile.square}",
        "",
        f"Images required: {len(plan.images)}",
        "",
        "Mark each progress column `yes` once that step is done. "
        "`blog-assets check` refuses to pass a delivery with a `no` left in it.",
        "",
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "|".join(["---:"] + ["---"] * (len(_COLUMNS) - 1)) + "|",
    ]
    for image in plan.images:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(image.position),
                    _cell(image.role),
                    _cell(image.level),
                    _cell(image.heading),
                    _cell(str(image.line) if image.line else ""),
                    _cell(image.anchor),
                    _cell(image.filename),
                    _cell(image.size),
                    PENDING,
                    PENDING,
                    PENDING,
                    _cell("; ".join(image.notes)),
                ]
            )
            + " |"
        )

    if plan.excluded:
        lines += [
            "",
            f"## Headings left out ({len(plan.excluded)}) — confirm each one",
            "",
            "| Level | Heading | Line | Reason |",
            "|---|---|---:|---|",
        ]
        for item in plan.excluded:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(item["level"].upper()),
                        _cell(item["text"] or "(empty)"),
                        _cell(str(item["line"])),
                        _cell(item["reason"] or ""),
                    ]
                )
                + " |"
            )
        lines += [
            "",
            "A body heading listed here means the page was saved in a form the "
            "parser could not read as article text. Add it to the table above by hand.",
        ]

    return "\n".join(lines) + "\n"


def parse(path: Path) -> list[LedgerRow]:
    """Read the delivery table back out of a hand-edited ledger."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise LedgerError(f"cannot read {path}: {exc}") from exc

    header: list[str] = []
    rows: list[LedgerRow] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0] == "#":
            header = cells
            in_table = True
            continue
        if not in_table or _SEPARATOR.match(stripped):
            continue
        record = dict(zip(header, cells))
        filename = record.get("Filename", "").strip("`")
        if not filename or filename == "-":
            continue
        try:
            position = int(record.get("#", "0"))
        except ValueError as exc:
            raise LedgerError(f"row for {filename}: '#' is not a number") from exc
        rows.append(
            LedgerRow(
                position=position,
                role=record.get("Role", "").lower(),
                filename=filename,
                size=record.get("Size", ""),
                heading=record.get("Heading", ""),
                progress={name: record.get(name, PENDING).lower() for name in PROGRESS_COLUMNS},
            )
        )

    if not rows:
        raise LedgerError(
            f"{path}: no delivery rows found. The table needs a header row "
            f"starting with '#' and a 'Filename' column."
        )
    return rows
