"""Turn an article's headings into the list of images a delivery must contain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .headings import Article
from .naming import char_limited, deduplicate, filename_stem, numbered
from .profile import DeliveryProfile, ProfileError

ROLE_HEADER = "header"
ROLE_BODY = "body"
ROLE_SQUARE = "square"


@dataclass
class PlannedImage:
    """One image the delivery must contain, and why."""

    position: int
    role: str
    filename: str
    size: str
    heading: str = ""
    level: str = ""
    line: int | None = None
    anchor: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeliveryPlan:
    article: str
    slug: str
    profile: DeliveryProfile
    images: list[PlannedImage]
    excluded: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "article": self.article,
            "slug": self.slug,
            "profile": self.profile.to_dict(),
            "images": [image.to_dict() for image in self.images],
            "excluded": self.excluded,
        }


def build_plan(article: Article, profile: DeliveryProfile, slug: str | None = None) -> DeliveryPlan:
    """Lay out the delivery: one header, one image per heading, one square.

    The order is fixed because the reviewer checks the package by scanning a
    sorted file listing. The header is first, the social square is last, and
    the body images are in document order in between.
    """
    resolved_slug = char_limited(slug or article.title, profile.max_slug_chars, "article")

    # Reserve the "NN_" prefix and the extension from the byte budget.
    suffix_bytes = len(profile.file_suffix.encode("utf-8"))
    stem_budget = profile.max_filename_bytes - len("00_") - suffix_bytes
    if stem_budget < 1:
        raise ProfileError(
            f"max_filename_bytes={profile.max_filename_bytes} leaves no room for a name"
        )
    # The slug is reused for the square image, which adds "_sq".
    slug_budget = stem_budget - len("_sq")
    short_slug = filename_stem(resolved_slug, max(slug_budget, 1), "article")

    body_headings = article.image_headings
    stems = deduplicate(
        [filename_stem(heading.text, stem_budget, "heading") for heading in body_headings]
    )

    images: list[PlannedImage] = [
        PlannedImage(
            position=1,
            role=ROLE_HEADER,
            filename=numbered(1, short_slug, profile.file_suffix),
            size=str(profile.size_for(ROLE_HEADER)),
        )
    ]

    for offset, (heading, stem) in enumerate(zip(body_headings, stems), start=2):
        notes = list(heading.notes)
        if stem != filename_stem(heading.text, stem_budget, "heading"):
            notes.append("numbered to keep the filename unique")
        if len(heading.text.encode("utf-8")) > stem_budget:
            notes.append("filename shortened to fit the byte limit")
        images.append(
            PlannedImage(
                position=offset,
                role=ROLE_BODY,
                filename=numbered(offset, stem, profile.file_suffix),
                size=str(profile.size_for(ROLE_BODY)),
                heading=heading.text,
                level=heading.level.upper(),
                line=heading.line,
                anchor=heading.anchor,
                notes=notes,
            )
        )

    last = len(images) + 1
    images.append(
        PlannedImage(
            position=last,
            role=ROLE_SQUARE,
            filename=numbered(last, f"{short_slug}_sq", profile.file_suffix),
            size=str(profile.size_for(ROLE_SQUARE)),
        )
    )

    excluded = [
        {
            "level": heading.level,
            "text": heading.text,
            "line": heading.line,
            "reason": heading.excluded,
        }
        for heading in article.excluded
    ]
    return DeliveryPlan(
        article=article.title,
        slug=resolved_slug,
        profile=profile,
        images=images,
        excluded=excluded,
    )
