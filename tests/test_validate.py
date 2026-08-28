"""Delivery validation, driven through a helper that builds a passing
delivery so each test can break exactly one rule."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from blog_asset_pipeline.headings import extract
from blog_asset_pipeline.ledger import parse, render
from blog_asset_pipeline.plan import build_plan
from blog_asset_pipeline.profile import DEFAULT_PROFILE, Size
from blog_asset_pipeline.validate import validate_delivery

from .conftest import write_png


def build_delivery(tmp_path: Path, fixtures: Path, complete: bool = True) -> Path:
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    plan = build_plan(extract(fixtures / "sample_article.html"), DEFAULT_PROFILE)

    ledger = render(plan)
    if complete:
        ledger = ledger.replace("| no | no | no |", "| yes | yes | yes |")
    (delivery / "ledger.md").write_text(ledger, encoding="utf-8")

    alt_lines = ["# Alt text", ""]
    for image in plan.images:
        size = Size.parse(image.size)
        write_png(delivery / image.filename, size.width, size.height)
        alt_lines.append(f"- `{image.filename}`: a plain description of the image")
    (delivery / "alt-text.md").write_text("\n".join(alt_lines) + "\n", encoding="utf-8")
    return delivery


def test_a_complete_delivery_passes(tmp_path, fixtures):
    report = validate_delivery(build_delivery(tmp_path, fixtures), DEFAULT_PROFILE)
    assert report.ok, [str(f) for f in report.failures]
    assert len(report.passed) == report.checked


def test_missing_file_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    next(delivery.glob("03_*.png")).unlink()
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("missing" in str(f) for f in report.failures)


def test_wrong_dimensions_are_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    target = next(delivery.glob("02_*.png"))
    write_png(target, 800, 600)
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("800x600" in str(f) for f in report.failures)


def test_empty_file_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    target = next(delivery.glob("02_*.png"))
    target.write_bytes(b"")
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("empty" in str(f) for f in report.failures)


def test_stray_image_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    write_png(delivery / "draft-version.png", 100, 100)
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("not in the ledger" in str(f) for f in report.failures)


def test_unfinished_progress_column_blocks_the_delivery(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures, complete=False)
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("progress not recorded" in str(f) for f in report.failures)


def test_missing_alt_text_file_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    (delivery / "alt-text.md").unlink()
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("alt-text.md not found" in str(f) for f in report.failures)


def test_missing_alt_text_for_one_image_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    alt = delivery / "alt-text.md"
    lines = [line for line in alt.read_text(encoding="utf-8").splitlines() if "02_" not in line]
    alt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("no alt text" in str(f) for f in report.failures)


def test_a_decomposed_filename_on_disk_still_matches_the_ledger(tmp_path, fixtures):
    """macOS writes NFD; the ledger holds NFC. That must not read as missing."""
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    heading = "ガーデニング"
    (delivery / "ledger.md").write_text(
        "| # | Role | Filename | Size | Generated | Reviewed | Alt |\n"
        "|---:|---|---|---|---|---|---|\n"
        f"| 1 | header | 01_{heading}.png | 1600x1200 | yes | yes | yes |\n"
        f"| 2 | square | 02_{heading}_sq.png | 1080x1080 | yes | yes | yes |\n",
        encoding="utf-8",
    )
    write_png(delivery / unicodedata.normalize("NFD", f"01_{heading}.png"), 1600, 1200)
    write_png(delivery / unicodedata.normalize("NFD", f"02_{heading}_sq.png"), 1080, 1080)
    (delivery / "alt-text.md").write_text(
        f"- 01_{heading}.png: description\n- 02_{heading}_sq.png: description\n", encoding="utf-8"
    )
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert report.ok, [str(f) for f in report.failures]


def test_missing_ledger_is_reported_without_a_traceback(tmp_path):
    empty = tmp_path / "delivery"
    empty.mkdir()
    report = validate_delivery(empty, DEFAULT_PROFILE)
    assert not report.ok
    assert any("ledger.md not found" in str(f) for f in report.failures)


def test_missing_delivery_folder_is_reported(tmp_path):
    report = validate_delivery(tmp_path / "nope", DEFAULT_PROFILE)
    assert any("not found" in str(f) for f in report.failures)


def test_square_image_out_of_position_is_reported(tmp_path, fixtures):
    delivery = build_delivery(tmp_path, fixtures)
    ledger = delivery / "ledger.md"
    text = ledger.read_text(encoding="utf-8").replace("| body |", "| square |", 1)
    ledger.write_text(text, encoding="utf-8")
    report = validate_delivery(delivery, DEFAULT_PROFILE)
    assert any("exactly one square" in str(f) for f in report.failures)


def test_ledger_columns_are_matched_by_name_not_position(tmp_path):
    """A hand-added column must not shift the parser off the filename."""
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "| # | Owner | Role | Filename | Size | Generated | Reviewed | Alt |\n"
        "|---:|---|---|---|---|---|---|---|\n"
        "| 1 | me | header | 01_intro.png | 1600x1200 | yes | yes | yes |\n"
        "| 2 | you | square | 02_intro_sq.png | 1080x1080 | yes | no | yes |\n",
        encoding="utf-8",
    )
    rows = parse(ledger)
    assert [row.filename for row in rows] == ["01_intro.png", "02_intro_sq.png"]
    assert rows[0].pending() == []
    assert rows[1].pending() == ["Reviewed"]
