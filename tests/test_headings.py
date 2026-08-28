import pytest

from blog_asset_pipeline.headings import SourceError, extract, read_source


def test_navigation_contents_and_footer_headings_are_excluded(fixtures):
    article = extract(fixtures / "sample_article.html")
    kept = [h.text for h in article.image_headings]
    assert "Site navigation" not in kept
    assert "Contents" not in kept
    assert "Footer links" not in kept
    reasons = {h.text: h.excluded for h in article.excluded}
    assert reasons["Contents"] == "table of contents"
    assert reasons["Footer links"] == "inside <footer>"


def test_shared_blocks_after_the_summary_are_dropped(fixtures):
    article = extract(fixtures / "sample_article.html")
    kept = [h.text for h in article.image_headings]
    assert kept[-1] == "Summary"
    assert "About the author" not in kept
    assert "Subscribe to the newsletter" not in kept


def test_body_headings_keep_document_order_and_level(fixtures):
    article = extract(fixtures / "sample_article.html")
    assert [(h.level, h.text) for h in article.image_headings] == [
        ("h2", "Why fixed schedules fail"),
        ("h3", "Read the soil, not the calendar"),
        ("h2", "Light and season change everything"),
        ("h2", "Pots without drainage"),
        ("h2", "Summary"),
    ]


def test_title_comes_from_the_article_not_the_site_name(fixtures):
    article = extract(fixtures / "sample_article.html")
    assert article.title == "Choosing a Watering Schedule for Indoor Plants"


def test_short_sections_are_flagged_but_not_removed(fixtures):
    article = extract(fixtures / "sample_article.html")
    short = next(h for h in article.image_headings if h.text == "Pots without drainage")
    assert any("short section" in note for note in short.notes)


def test_duplicate_headings_are_flagged(fixtures):
    article = extract(fixtures / "duplicate_headings.html")
    second = [h for h in article.image_headings if h.text == "Notes"][1]
    assert any("duplicate" in note for note in second.notes)


def test_missing_anchor_is_flagged(fixtures):
    article = extract(fixtures / "duplicate_headings.html")
    second = [h for h in article.image_headings if h.text == "Notes"][1]
    assert "no anchor id" in second.notes


def test_markdown_draft_is_accepted_as_a_fallback(fixtures):
    article = extract(fixtures / "draft.md")
    assert [h.text for h in article.image_headings] == [
        "First section",
        "A sub-section",
        "Summary",
    ]


def test_declared_encoding_wins_over_utf8(tmp_path):
    # A page saved as cp932 must not be silently decoded as UTF-8.
    path = tmp_path / "legacy.html"
    text = "<html><head><meta charset='Shift_JIS'><title>設定</title></head><body><h2>本文</h2></body></html>"
    path.write_bytes(text.encode("cp932"))
    source, encoding = read_source(path)
    assert encoding.lower() in ("shift_jis", "cp932")
    assert "本文" in source


def test_empty_file_is_an_error_not_an_empty_plan(tmp_path):
    path = tmp_path / "empty.html"
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(SourceError, match="empty"):
        extract(path)


def test_directory_argument_is_rejected(tmp_path):
    with pytest.raises(SourceError, match="directory"):
        extract(tmp_path)


def test_malformed_markup_still_yields_the_headings_it_could_read(tmp_path):
    path = tmp_path / "messy.html"
    path.write_text(
        "<h1>Title</h1><h2 id='a'>Kept<p>body text that is long enough to count"
        "<h2 id='b'>Also kept</h2>",
        encoding="utf-8",
    )
    article = extract(path)
    assert [h.text for h in article.image_headings] == ["Kept", "Also kept"]
