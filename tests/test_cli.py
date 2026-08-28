"""End-to-end runs of the command line, the way it is actually used."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from blog_asset_pipeline.cli import main
from blog_asset_pipeline.ledger import parse
from blog_asset_pipeline.profile import Size

from .conftest import write_png


def prepare_delivery(delivery: Path) -> None:
    """Fill in a planned delivery: images, alt text, progress marked done."""
    rows = parse(delivery / "ledger.md")
    alt = ["# Alt text", ""]
    for row in rows:
        size = Size.parse(row.size)
        write_png(delivery / row.filename, size.width, size.height)
        alt.append(f"- `{row.filename}`: description")
    (delivery / "alt-text.md").write_text("\n".join(alt) + "\n", encoding="utf-8")
    ledger = delivery / "ledger.md"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace("| no | no | no |", "| yes | yes | yes |"),
        encoding="utf-8",
    )


def test_plan_then_check_then_archive(tmp_path, fixtures, capsys):
    delivery = tmp_path / "delivery"

    assert main(["plan", str(fixtures / "sample_article.html"), "--out", str(delivery)]) == 0
    assert (delivery / "ledger.md").exists()
    plan = json.loads((delivery / "plan.json").read_text(encoding="utf-8"))
    assert plan["article"] == "Choosing a Watering Schedule for Indoor Plants"

    assert main(["check", str(delivery)]) == 1  # nothing produced yet

    prepare_delivery(delivery)
    assert main(["check", str(delivery)]) == 0

    archive = tmp_path / "delivery.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for entry in sorted(delivery.iterdir()):
            zipped.write(entry, f"delivery/{entry.name}")
    assert main(["check-archive", str(delivery), str(archive)]) == 0

    output = capsys.readouterr().out
    assert "Images in the delivery" in output


def test_plan_refuses_to_overwrite_recorded_progress(tmp_path, fixtures, capsys):
    delivery = tmp_path / "delivery"
    main(["plan", str(fixtures / "sample_article.html"), "--out", str(delivery)])
    prepare_delivery(delivery)

    main(["plan", str(fixtures / "sample_article.html"), "--out", str(delivery)])
    assert (delivery / "ledger.new.md").exists()
    assert "yes | yes | yes" in (delivery / "ledger.md").read_text(encoding="utf-8")

    main(["plan", str(fixtures / "sample_article.html"), "--out", str(delivery), "--force"])
    assert "| no | no | no |" in (delivery / "ledger.md").read_text(encoding="utf-8")


def test_plan_fails_when_the_page_has_no_body_headings(tmp_path, capsys):
    page = tmp_path / "listing.html"
    page.write_text("<html><body><nav><h2>Links</h2></nav></body></html>", encoding="utf-8")
    assert main(["plan", str(page)]) == 1
    assert "No body headings" in capsys.readouterr().err


def test_a_bad_profile_reports_an_error_not_a_traceback(tmp_path, fixtures, capsys):
    profile = tmp_path / "profile.json"
    profile.write_text("{not json", encoding="utf-8")
    assert main(["plan", str(fixtures / "sample_article.html"), "--profile", str(profile)]) == 2
    assert "error:" in capsys.readouterr().err


def test_a_missing_article_reports_an_error(tmp_path, capsys):
    assert main(["plan", str(tmp_path / "gone.html")]) == 2
    assert "error:" in capsys.readouterr().err


def test_custom_profile_changes_the_planned_sizes(tmp_path, fixtures, capsys):
    profile = tmp_path / "profile.json"
    profile.write_text('{"name": "wide", "header": "1920x1080"}', encoding="utf-8")
    assert main(["plan", str(fixtures / "sample_article.html"), "--profile", str(profile)]) == 0
    assert "1920x1080" in capsys.readouterr().out
