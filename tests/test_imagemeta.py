import pytest

from blog_asset_pipeline.imagemeta import ImageFormatError, image_size, try_image_size

from .conftest import write_gif, write_jpeg, write_png, write_webp


@pytest.mark.parametrize(
    "writer, name",
    [(write_png, "a.png"), (write_gif, "a.gif"), (write_jpeg, "a.jpg"), (write_webp, "a.webp")],
)
def test_reads_dimensions_of_every_supported_format(tmp_path, writer, name):
    assert image_size(writer(tmp_path / name, 1200, 900)) == (1200, 900)


def test_jpeg_dimensions_are_found_behind_a_metadata_segment(tmp_path):
    # The frame header is not at a fixed offset, so the segments are walked.
    assert image_size(write_jpeg(tmp_path / "meta.jpg", 640, 480)) == (640, 480)


def test_empty_file_is_reported_not_guessed(tmp_path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(ImageFormatError, match="empty"):
        image_size(empty)


def test_text_file_with_an_image_extension_is_rejected(tmp_path):
    fake = tmp_path / "not-really.png"
    fake.write_text("this is a text file", encoding="utf-8")
    with pytest.raises(ImageFormatError):
        image_size(fake)


def test_truncated_png_header_is_reported(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4)
    with pytest.raises(ImageFormatError, match="truncated"):
        image_size(broken)


def test_try_image_size_returns_a_reason_instead_of_raising(tmp_path):
    missing = tmp_path / "gone.png"
    size, reason = try_image_size(missing)
    assert size is None
    assert reason
