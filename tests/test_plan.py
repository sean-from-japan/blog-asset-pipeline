import pytest

from blog_asset_pipeline.headings import extract
from blog_asset_pipeline.ledger import parse, render
from blog_asset_pipeline.naming import filename_bytes
from blog_asset_pipeline.plan import build_plan
from blog_asset_pipeline.profile import DEFAULT_PROFILE, DeliveryProfile, ProfileError, Size


def test_plan_is_header_then_body_images_then_square(fixtures):
    plan = build_plan(extract(fixtures / "sample_article.html"), DEFAULT_PROFILE)
    assert [image.role for image in plan.images] == [
        "header",
        "body",
        "body",
        "body",
        "body",
        "body",
        "square",
    ]
    assert plan.images[0].size == "1600x1200"
    assert plan.images[-1].size == "1080x1080"


def test_every_filename_is_numbered_in_order(fixtures):
    plan = build_plan(extract(fixtures / "sample_article.html"), DEFAULT_PROFILE)
    for index, image in enumerate(plan.images, start=1):
        assert image.filename.startswith(f"{index:02d}_")


def test_every_planned_filename_fits_the_byte_budget(fixtures):
    long_titles = DeliveryProfile(max_filename_bytes=40)
    plan = build_plan(extract(fixtures / "sample_article.html"), long_titles)
    for image in plan.images:
        assert filename_bytes(image.filename) <= long_titles.max_filename_bytes


def test_duplicate_headings_get_distinct_filenames(fixtures):
    plan = build_plan(extract(fixtures / "duplicate_headings.html"), DEFAULT_PROFILE)
    names = [image.filename for image in plan.images]
    assert len(names) == len(set(names))


def test_ledger_round_trips_through_the_parser(tmp_path, fixtures):
    plan = build_plan(extract(fixtures / "sample_article.html"), DEFAULT_PROFILE)
    path = tmp_path / "ledger.md"
    path.write_text(render(plan), encoding="utf-8")
    rows = parse(path)
    assert [row.filename for row in rows] == [image.filename for image in plan.images]
    assert [row.position for row in rows] == list(range(1, len(plan.images) + 1))


def test_ledger_starts_every_row_as_pending(tmp_path, fixtures):
    plan = build_plan(extract(fixtures / "sample_article.html"), DEFAULT_PROFILE)
    path = tmp_path / "ledger.md"
    path.write_text(render(plan), encoding="utf-8")
    assert all(row.pending() for row in parse(path))


def test_a_pipe_in_a_heading_cannot_break_the_table(tmp_path):
    source = tmp_path / "piped.html"
    source.write_text(
        "<h1>T</h1><h2 id='a'>Cost | benefit</h2><p>" + "x" * 60 + "</p>", encoding="utf-8"
    )
    plan = build_plan(extract(source), DEFAULT_PROFILE)
    ledger = tmp_path / "ledger.md"
    ledger.write_text(render(plan), encoding="utf-8")
    rows = parse(ledger)
    assert len(rows) == 3


def test_profile_loads_from_json(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"name": "wide", "header": "1920x1080"}', encoding="utf-8")
    profile = DeliveryProfile.load(path)
    assert profile.header == Size(1920, 1080)
    assert profile.body == DEFAULT_PROFILE.body


def test_profile_rejects_unknown_keys(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"headr": "1920x1080"}', encoding="utf-8")
    with pytest.raises(ProfileError, match="unknown profile keys"):
        DeliveryProfile.load(path)


def test_profile_rejects_a_malformed_size(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"header": "wide"}', encoding="utf-8")
    with pytest.raises(ProfileError, match="not a size"):
        DeliveryProfile.load(path)
