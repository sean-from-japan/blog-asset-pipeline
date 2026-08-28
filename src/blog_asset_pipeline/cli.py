"""Command line entry point: ``blog-assets plan | check | check-archive``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .headings import SourceError, extract
from .ledger import LedgerError, render
from .package_check import validate_package
from .plan import build_plan
from .profile import DEFAULT_PROFILE, DeliveryProfile, ProfileError
from .validate import LEDGER_NAME, format_report, validate_delivery

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2


def _load_profile(path: str | None) -> DeliveryProfile:
    return DeliveryProfile.load(Path(path)) if path else DEFAULT_PROFILE


def _cmd_plan(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    article = extract(Path(args.article), profile.min_body_chars, args.title)
    plan = build_plan(article, profile, args.slug)

    body = len(article.image_headings)
    print(f"Article: {plan.article}")
    print(f"Read as: {article.encoding}")
    print(f"Headings with an image: {body}")
    print(f"Images in the delivery: {len(plan.images)}")
    for image in plan.images:
        note = f"  [{'; '.join(image.notes)}]" if image.notes else ""
        print(f"  {image.position:>2}. {image.filename:<44} {image.size:<10} {image.role}{note}")
    if plan.excluded:
        print(f"\nHeadings left out ({len(plan.excluded)}) — confirm each one:")
        for item in plan.excluded:
            print(
                f"  {item['level'].upper():<3} line {item['line']:<5} {item['text']!r} — {item['reason']}"
            )

    if body == 0:
        print(
            "\nNo body headings were found, so no ledger was written. "
            "Check that the file is the article and not a listing page.",
            file=sys.stderr,
        )
        return EXIT_PROBLEMS
    if len(plan.excluded) > body:
        print(
            f"\nWarning: more headings were left out ({len(plan.excluded)}) than kept ({body}). "
            "The page may have been saved in an unexpected form.",
            file=sys.stderr,
        )

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = out_dir / LEDGER_NAME
        if ledger_path.exists() and not args.force:
            ledger_path = out_dir / "ledger.new.md"
            print(
                f"\n{LEDGER_NAME} already exists; writing {ledger_path.name} instead so "
                "recorded progress is not lost. Use --force to replace it.",
                file=sys.stderr,
            )
        ledger_path.write_text(render(plan), encoding="utf-8")
        (out_dir / "plan.json").write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nWrote {ledger_path} and {out_dir / 'plan.json'}")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    directory = Path(args.delivery)
    report = validate_delivery(directory, profile)
    print(format_report(report, directory))
    return EXIT_OK if report.ok else EXIT_PROBLEMS


def _cmd_check_archive(args: argparse.Namespace) -> int:
    directory = Path(args.delivery)
    report = validate_package(directory, Path(args.archive))
    print(format_report(report, directory))
    return EXIT_OK if report.ok else EXIT_PROBLEMS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blog-assets",
        description="Plan, check and package the images that go with an article.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="read an article and write the delivery ledger")
    plan.add_argument("article", help="saved HTML page or Markdown draft")
    plan.add_argument("--out", help="delivery folder to write ledger.md and plan.json into")
    plan.add_argument("--title", help="article name (default: page title or first h1)")
    plan.add_argument("--slug", help="basename for the header and square images")
    plan.add_argument("--profile", help="path to a delivery profile JSON file")
    plan.add_argument("--force", action="store_true", help="replace an existing ledger.md")
    plan.set_defaults(func=_cmd_plan)

    check = sub.add_parser("check", help="check a delivery folder against its ledger")
    check.add_argument("delivery")
    check.add_argument("--profile", help="path to a delivery profile JSON file")
    check.set_defaults(func=_cmd_check)

    archive = sub.add_parser("check-archive", help="check the zip against the delivery folder")
    archive.add_argument("delivery")
    archive.add_argument("archive")
    archive.set_defaults(func=_cmd_check_archive)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SourceError, LedgerError, ProfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
