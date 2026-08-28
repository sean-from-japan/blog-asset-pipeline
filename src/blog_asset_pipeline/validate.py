"""Check a delivery directory against its ledger.

Every rule here exists because breaking it caused rework once: a file the
CMS silently renamed, an image at the wrong aspect ratio, an alt text that
was never written, a leftover draft uploaded by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .imagemeta import try_image_size
from .ledger import PROGRESS_COLUMNS, LedgerRow, parse
from .naming import filename_bytes, nfc
from .profile import DeliveryProfile, Size

LEDGER_NAME = "ledger.md"
ALT_TEXT_NAME = "alt-text.md"


@dataclass
class Finding:
    filename: str
    problem: str

    def __str__(self) -> str:
        return f"{self.filename}: {self.problem}" if self.filename else self.problem


@dataclass
class Report:
    checked: int = 0
    failures: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def fail(self, filename: str, problem: str) -> None:
        self.failures.append(Finding(filename, problem))

    def warn(self, filename: str, problem: str) -> None:
        self.warnings.append(Finding(filename, problem))


def _read_alt_text(directory: Path) -> str | None:
    path = directory / ALT_TEXT_NAME
    if not path.exists():
        return None
    return nfc(path.read_text(encoding="utf-8", errors="replace"))


def _check_order(rows: list[LedgerRow], report: Report) -> None:
    """The package is reviewed as a sorted listing, so order is a rule."""
    if rows[0].role != "header":
        report.fail("", "the first row must be the header image")
    if rows[-1].role != "square":
        report.fail("", "the last row must be the square image")
    squares = [row.position for row in rows if row.role == "square"]
    if squares != [rows[-1].position]:
        report.fail("", f"expected exactly one square image, last; found positions {squares}")
    for expected, row in enumerate(rows, start=1):
        if row.position != expected:
            report.fail(row.filename, f"ledger position {row.position}, expected {expected}")


def validate_delivery(directory: Path, profile: DeliveryProfile) -> Report:
    """Validate one delivery folder. The report lists every problem found."""
    report = Report()

    if not directory.is_dir():
        report.fail("", f"delivery folder not found: {directory}")
        return report

    ledger_path = directory / LEDGER_NAME
    if not ledger_path.exists():
        report.fail("", f"{LEDGER_NAME} not found in {directory}")
        return report

    rows = parse(ledger_path)
    report.checked = len(rows)
    _check_order(rows, report)

    duplicates = {
        row.filename for row in rows if [r.filename for r in rows].count(row.filename) > 1
    }
    for filename in sorted(duplicates):
        report.fail(filename, "listed more than once in the ledger")

    alt_text = _read_alt_text(directory)
    if alt_text is None:
        report.fail("", f"{ALT_TEXT_NAME} not found; alt text is part of the delivery")

    # macOS stores directory entries decomposed; the ledger is composed.
    on_disk = {nfc(entry.name): entry.name for entry in directory.iterdir()}

    for index, row in enumerate(rows, start=1):
        key = nfc(row.filename)
        if key not in on_disk:
            report.fail(row.filename, "file is missing")
            continue

        path = directory / on_disk[key]
        problems: list[str] = []

        actual_bytes = filename_bytes(on_disk[key])
        if actual_bytes > profile.max_filename_bytes:
            problems.append(
                f"filename is {actual_bytes} bytes, over the {profile.max_filename_bytes}-byte limit"
            )
        if not row.filename.startswith(f"{index:02d}_"):
            problems.append(f"filename should start with '{index:02d}_'")
        if path.stat().st_size == 0:
            problems.append("file is empty")

        size, reason = try_image_size(path)
        if size is None:
            problems.append(reason or "not a readable image")
        elif row.size and row.size != "-":
            expected = Size.parse(row.size)
            if (expected.width, expected.height) != size:
                problems.append(f"is {size[0]}x{size[1]}, ledger says {expected}")

        if alt_text is not None and key not in alt_text:
            problems.append(f"no alt text for it in {ALT_TEXT_NAME}")

        pending = row.pending()
        if pending:
            problems.append("progress not recorded: " + ", ".join(pending))

        if problems:
            for problem in problems:
                report.fail(row.filename, problem)
        else:
            report.passed.append(row.filename)

    listed = {nfc(row.filename) for row in rows}
    strays = sorted(
        name
        for name in on_disk
        if name not in listed and Path(name).suffix.lower() in profile.image_suffixes
    )
    for stray in strays:
        report.fail(stray, "image is in the folder but not in the ledger")

    return report


def format_report(report: Report, directory: Path) -> str:
    lines = [f"Delivery: {directory}", f"Ledger rows: {report.checked}", ""]
    for name in report.passed:
        lines.append(f"  ok    {name}")
    for finding in report.failures:
        lines.append(f"  FAIL  {finding}")
    for finding in report.warnings:
        lines.append(f"  warn  {finding}")
    lines += [
        "",
        f"{len(report.passed)} ready, {len(report.failures)} problem(s), "
        f"{len(report.warnings)} warning(s)",
    ]
    return "\n".join(lines)


def progress_columns() -> dict[str, str]:
    """Exposed so the CLI help and the ledger template cannot drift apart."""
    return {name: "yes / no" for name in PROGRESS_COLUMNS}
