"""Check the archive that is actually sent, not the folder it came from.

Zipping a folder is the step where working files sneak back in: a nested
``drafts/`` directory, a macOS metadata file, a duplicate entry from a
re-zip. The archive is compared against the folder it should mirror.
"""

from __future__ import annotations

import collections
import zipfile
from pathlib import Path

from .validate import Report


def _relative_names(names: list[str]) -> list[str]:
    """Strip the single wrapping directory that archive tools add."""
    files = [name for name in names if not name.endswith("/")]
    if not files:
        return []
    roots = {name.split("/", 1)[0] for name in files if "/" in name}
    if len(roots) == 1 and all("/" in name for name in files):
        prefix = f"{roots.pop()}/"
        return [name[len(prefix) :] for name in files]
    return files


def validate_package(directory: Path, archive_path: Path) -> Report:
    report = Report()

    if not directory.is_dir():
        report.fail("", f"delivery folder not found: {directory}")
    if not archive_path.is_file():
        report.fail("", f"archive not found: {archive_path}")
    if report.failures:
        return report

    expected = sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and not entry.name.startswith(".")
    )

    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            damaged = archive.testzip()
    except zipfile.BadZipFile as exc:
        report.fail(archive_path.name, f"not a readable zip archive ({exc})")
        return report

    relative = _relative_names(names)
    report.checked = len(relative)

    if damaged:
        report.fail(damaged, "entry fails its checksum")

    duplicates = sorted(name for name, count in collections.Counter(names).items() if count > 1)
    for name in duplicates:
        report.fail(name, "appears twice in the archive")

    for name in sorted(n for n in relative if "/" in n):
        report.fail(name, "is inside a sub-folder; only the delivery files belong in the archive")

    for name in sorted(n for n in relative if any(p.startswith(".") for p in n.split("/"))):
        report.fail(name, "is a hidden file")

    packaged = sorted(name for name in relative if "/" not in name)
    missing = sorted(set(expected) - set(packaged))
    extra = sorted(set(packaged) - set(expected))
    for name in missing:
        report.fail(name, "is in the delivery folder but not in the archive")
    for name in extra:
        report.fail(name, "is in the archive but not in the delivery folder")

    if not report.failures:
        report.passed.extend(packaged)
    return report
