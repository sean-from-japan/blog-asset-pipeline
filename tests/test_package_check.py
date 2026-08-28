import zipfile
from pathlib import Path

from blog_asset_pipeline.package_check import validate_package

from .conftest import write_png


def make_delivery(tmp_path: Path) -> Path:
    delivery = tmp_path / "delivery"
    (delivery / "work").mkdir(parents=True)
    write_png(delivery / "01_intro.png", 100, 100)
    write_png(delivery / "02_intro_sq.png", 100, 100)
    (delivery / "ledger.md").write_text("ledger", encoding="utf-8")
    (delivery / "alt-text.md").write_text("alt", encoding="utf-8")
    write_png(delivery / "work" / "draft.png", 10, 10)
    (delivery / ".DS_Store").write_bytes(b"\x00")
    return delivery


def zip_names(path: Path, names, root: str = "delivery") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(f"{root}/{name}" if root else name, "x")
    return path


def test_a_clean_archive_passes(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(
        tmp_path / "ok.zip", ["01_intro.png", "02_intro_sq.png", "ledger.md", "alt-text.md"]
    )
    report = validate_package(delivery, archive)
    assert report.ok, [str(f) for f in report.failures]


def test_a_working_sub_folder_is_reported(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(
        tmp_path / "nested.zip",
        ["01_intro.png", "02_intro_sq.png", "ledger.md", "alt-text.md", "work/draft.png"],
    )
    report = validate_package(delivery, archive)
    assert any("sub-folder" in str(f) for f in report.failures)


def test_a_hidden_file_is_reported(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(
        tmp_path / "hidden.zip",
        ["01_intro.png", "02_intro_sq.png", "ledger.md", "alt-text.md", ".DS_Store"],
    )
    report = validate_package(delivery, archive)
    assert any("hidden" in str(f) for f in report.failures)


def test_a_file_missing_from_the_archive_is_reported(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(tmp_path / "short.zip", ["01_intro.png", "ledger.md", "alt-text.md"])
    report = validate_package(delivery, archive)
    assert any("not in the archive" in str(f) for f in report.failures)


def test_an_extra_file_in_the_archive_is_reported(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(
        tmp_path / "extra.zip",
        ["01_intro.png", "02_intro_sq.png", "ledger.md", "alt-text.md", "notes.txt"],
    )
    report = validate_package(delivery, archive)
    assert any("not in the delivery folder" in str(f) for f in report.failures)


def test_an_archive_without_a_wrapping_folder_is_accepted(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = zip_names(
        tmp_path / "flat.zip",
        ["01_intro.png", "02_intro_sq.png", "ledger.md", "alt-text.md"],
        root="",
    )
    report = validate_package(delivery, archive)
    assert report.ok, [str(f) for f in report.failures]


def test_a_corrupt_file_is_reported_not_ignored(tmp_path):
    delivery = make_delivery(tmp_path)
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"not a zip at all")
    report = validate_package(delivery, archive)
    assert any("zip" in str(f).lower() for f in report.failures)


def test_a_missing_archive_is_reported(tmp_path):
    delivery = make_delivery(tmp_path)
    report = validate_package(delivery, tmp_path / "absent.zip")
    assert any("not found" in str(f) for f in report.failures)
