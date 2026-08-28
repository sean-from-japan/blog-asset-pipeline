"""Recover the heading structure of an article from a saved page.

The input is whatever the writer can actually hand over: a page saved from a
content management system's preview, or a Markdown draft. Neither is a clean
document tree, so the parser is written to be tolerant and to *report* what
it discarded instead of silently dropping it. A heading that disappears
without a trace is the failure that costs a redelivery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

HEADING_TAGS = ("h1", "h2", "h3", "h4")

#: Elements whose headings are chrome, not article body.
NON_BODY_TAGS = frozenset(
    {"nav", "aside", "footer", "header", "script", "style", "template", "noscript"}
)

#: Only containers are judged by class or id. Headings themselves often carry
#: ids such as ``toc-3`` that would otherwise be mistaken for a contents box.
CONTAINER_TAGS = frozenset({"div", "section", "ul", "ol", "table", "details", "form"})

#: A heading cannot legally contain any of these. Seeing one open while a
#: heading is still open means the heading was never closed.
BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "ul",
        "ol",
        "li",
        "table",
        "blockquote",
        "pre",
        "figure",
        "hr",
        "aside",
        "footer",
        "nav",
    }
)

_TOC_HINT = re.compile(r"\b(toc|table-of-contents|contents-list)\b", re.I)
_SUMMARY_HINT = re.compile(r"^(summary|in summary|conclusion|wrap[- ]up|takeaways)\b", re.I)
_WHITESPACE = re.compile(r"\s+")


class SourceError(ValueError):
    """Raised when the article source cannot be read at all."""


@dataclass
class Heading:
    """One heading, with the context needed to review and to place an image."""

    level: str
    text: str
    line: int
    anchor: str = ""
    body_chars: int = 0
    is_title: bool = False
    excluded: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return int(self.level[1])


@dataclass
class Article:
    title: str
    encoding: str
    headings: list[Heading]
    excluded: list[Heading]

    @property
    def image_headings(self) -> list[Heading]:
        """Headings that get their own image: everything below the title."""
        return [h for h in self.headings if h.level != "h1"]


def read_source(path: Path) -> tuple[str, str]:
    """Read the article, honouring a declared encoding before guessing.

    A page saved as legacy Japanese or Western European text decodes without
    error as UTF-8 in some byte sequences and produces silent mojibake, so
    the declared charset wins when there is one.
    """
    if path.is_dir():
        raise SourceError(f"{path} is a directory; pass the article file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceError(f"cannot read {path}: {exc}") from exc
    if not raw.strip():
        raise SourceError(f"{path} is empty")

    candidates: list[str] = []
    declared = re.search(rb'charset=["\']?\s*([\w-]+)', raw[:4096], re.I)
    if declared:
        candidates.append(declared.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "cp932", "euc_jp", "cp1252"]
    for encoding in candidates:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace"), "utf-8 (with replacements)"


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[Heading] = []
        self.excluded: list[Heading] = []
        self.page_title: str | None = None
        self._anchors: dict[str, str] = {}
        self._skip_stack: list[tuple[str, str]] = []
        self._current: Heading | None = None
        self._current_text: list[str] = []
        self._in_title = False

    def _skip_reason(self, tag: str, attrs: dict[str, str]) -> str | None:
        if tag in NON_BODY_TAGS:
            return f"inside <{tag}>"
        if tag not in CONTAINER_TAGS:
            return None
        blob = " ".join(attrs.get(key, "") for key in ("class", "id", "role"))
        return "table of contents" if _TOC_HINT.search(blob) else None

    def handle_starttag(self, tag, attrs):
        attributes = {key: (value or "") for key, value in attrs}

        if tag == "title":
            self._in_title = True
            return

        if self._current is not None and tag in BLOCK_TAGS:
            self._finish_current(note="heading tag was not closed")

        if tag in HEADING_TAGS:
            if self._current is not None:
                # An unclosed heading would otherwise be overwritten and lost
                # without a trace, which is the one failure mode that costs a
                # redelivery. Keep it and say why it looks odd.
                self._finish_current(note="heading tag was not closed")
            line, _ = self.getpos()
            classes = attributes.get("class", "")
            self._current = Heading(
                level=tag,
                text="",
                line=line,
                anchor=attributes.get("id", ""),
                is_title=tag == "h1" or "post-title" in classes or "entry-title" in classes,
                excluded=self._skip_stack[-1][1] if self._skip_stack else None,
            )
            self._current_text = []
            return

        reason = self._skip_reason(tag, attributes)
        if reason:
            self._skip_stack.append((tag, reason))

    def _finish_current(self, note: str | None = None) -> None:
        heading = self._current
        if heading is None:
            return
        heading.text = _WHITESPACE.sub(" ", "".join(self._current_text)).strip()
        self._current = None
        self._current_text = []
        if note:
            heading.notes.append(note)
        if not heading.text:
            heading.excluded = heading.excluded or "empty heading text"
        if heading.excluded:
            self.excluded.append(heading)
        else:
            self.headings.append(heading)

    def close(self):
        super().close()
        self._finish_current(note="heading tag was not closed")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            return
        if self._current is not None and tag == self._current.level:
            self._finish_current()
            return
        if self._skip_stack and self._skip_stack[-1][0] == tag:
            self._skip_stack.pop()

    def handle_data(self, data):
        if self._in_title and self.page_title is None:
            stripped = data.strip()
            if stripped:
                self.page_title = stripped
            return
        if self._current is not None:
            self._current_text.append(data)
        elif not self._skip_stack and self.headings:
            # Body text is attributed to the heading that introduced it; a
            # section with almost no text usually means a mis-parsed page.
            self.headings[-1].body_chars += len(data.strip())


def parse_markdown(source: str) -> list[Heading]:
    """Fallback for a Markdown draft handed over instead of a saved page."""
    headings: list[Heading] = []
    for number, line in enumerate(source.splitlines(), start=1):
        match = re.match(r"^(#{1,4})\s+(.*\S)\s*$", line)
        if match:
            level = f"h{len(match.group(1))}"
            headings.append(
                Heading(
                    level=level,
                    text=match.group(2).strip(),
                    line=number,
                    is_title=level == "h1",
                )
            )
        elif headings:
            headings[-1].body_chars += len(line.strip())
    return headings


def trim_trailing_blocks(
    headings: list[Heading], excluded: list[Heading]
) -> tuple[list[Heading], list[Heading]]:
    """Drop the shared blocks a CMS appends after the article's summary.

    Author profiles and calls to action are the same on every article and
    must not be counted as headings that need an image.
    """
    kept: list[Heading] = []
    ended = False
    for heading in headings:
        if ended and heading.level != "h1":
            heading.excluded = "shared block after the summary"
            excluded.append(heading)
            continue
        kept.append(heading)
        if heading.level != "h1" and _SUMMARY_HINT.match(heading.text):
            ended = True
    return kept, excluded


def clean_title(raw: str) -> str:
    """A page title is usually ``Article name | Site name``."""
    return re.split(r"\s*[|｜]\s*|\s+[-–]\s+", raw)[0].strip()


def annotate(headings: list[Heading], min_body_chars: int) -> list[Heading]:
    """Attach review notes. Notes never remove a heading, they flag it."""
    seen: dict[str, int] = {}
    for position, heading in enumerate(headings, start=1):
        if heading.level == "h1":
            continue
        first = seen.get(heading.text)
        if first is not None:
            heading.notes.append(f"duplicate of heading #{first}")
        else:
            seen[heading.text] = position
        if not heading.anchor:
            heading.notes.append("no anchor id")
        if heading.body_chars < min_body_chars:
            heading.notes.append(f"short section ({heading.body_chars} characters)")
    return headings


def extract(path: Path, min_body_chars: int = 30, title: str | None = None) -> Article:
    """Parse an article file into an :class:`Article`."""
    source, encoding = read_source(path)

    parser = _HeadingParser()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        parser.excluded.append(
            Heading(level="h?", text="", line=0, excluded=f"parser stopped early: {exc}")
        )

    headings, excluded = trim_trailing_blocks(parser.headings, parser.excluded)
    if not [h for h in headings if h.level != "h1"]:
        markdown = parse_markdown(source)
        if [h for h in markdown if h.level != "h1"]:
            headings, excluded = trim_trailing_blocks(markdown, [])
            encoding = f"{encoding} (read as Markdown)"

    annotate(headings, min_body_chars)

    resolved = title
    if not resolved:
        page_h1 = next((h.text for h in headings if h.is_title and h.text), None)
        resolved = page_h1 or (clean_title(parser.page_title) if parser.page_title else None)
    if not resolved:
        resolved = path.stem

    return Article(title=resolved, encoding=encoding, headings=headings, excluded=excluded)
