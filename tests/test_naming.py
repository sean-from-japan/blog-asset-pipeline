from blog_asset_pipeline.naming import (
    byte_limited,
    char_limited,
    deduplicate,
    filename_bytes,
    filename_stem,
    nfc,
    numbered,
    sanitize,
)


def test_illegal_characters_are_removed():
    assert sanitize('Before/After: "the fix"?') == "BeforeAfter the fix"


def test_trailing_punctuation_is_trimmed():
    assert sanitize("Does this work?") == "Does this work"


def test_byte_limit_counts_bytes_not_characters():
    # Three-byte characters exhaust a 40-byte budget after 13 of them, which
    # is the rule a character-based limit gets wrong.
    name = "あ" * 20
    trimmed = byte_limited(name, 40)
    assert len(trimmed) == 13
    assert filename_bytes(trimmed) <= 40


def test_byte_limit_never_splits_a_character():
    trimmed = byte_limited("あ" * 5, 8)
    assert trimmed.encode("utf-8").decode("utf-8") == trimmed


def test_byte_limit_falls_back_when_nothing_fits():
    assert byte_limited("ああ", 2, fallback="image") == "image"


def test_char_limit_is_independent_of_encoding():
    assert char_limited("あ" * 60, 50) == "あ" * 50


def test_duplicates_are_numbered_in_order():
    assert deduplicate(["notes", "room", "notes", "notes"]) == [
        "notes",
        "room",
        "notes_2",
        "notes_3",
    ]


def test_numbering_is_zero_padded():
    assert numbered(7, "intro", ".png") == "07_intro.png"


def test_decomposed_and_composed_names_compare_equal():
    composed = "ガ"  # GA
    decomposed = "ガ"  # KA + combining mark, as macOS stores it
    assert composed != decomposed
    assert nfc(composed) == nfc(decomposed)


def test_filename_stem_replaces_spaces_with_hyphens():
    assert filename_stem("Read the soil, not the calendar", 40) == "Read-the-soil-not-the-calendar"


def test_filename_stem_never_ends_in_a_hyphen():
    assert not filename_stem("Light and season change everything", 22).endswith("-")
