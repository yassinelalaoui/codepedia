from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from .models import PageLink

HOME_PAGE_ID = "home"
HOME_OUTPUT_MARKDOWN = "index.md"
HOME_OUTPUT_HTML = "index.html"

CLASS_DIAGRAM_PAGE_ID = "diagram:class-overview"
CLASS_DIAGRAM_OUTPUT_MARKDOWN = "diagrams/class-overview.md"
CLASS_DIAGRAM_OUTPUT_HTML = "diagrams/class-overview.html"

SEQUENCE_DIAGRAM_PAGE_ID_PREFIX = "sequence:"

USE_CASE_DIAGRAM_PAGE_ID = "diagram:use-case-overview"
USE_CASE_DIAGRAM_OUTPUT_MARKDOWN = "diagrams/use-case-overview.md"
USE_CASE_DIAGRAM_OUTPUT_HTML = "diagrams/use-case-overview.html"

SECTION_PAGE_ID_PREFIX = "section:"

DIAGRAMS_INDEX_PAGE_ID = "diagrams-index"
DIAGRAMS_INDEX_OUTPUT_MARKDOWN = "diagrams-index.md"
DIAGRAMS_INDEX_OUTPUT_HTML = "diagrams-index.html"


def module_page_id(module_id: str) -> str:
    return f"module:{module_id}"


def diagram_page_id(module_id: str) -> str:
    return f"diagram:{module_id}"


def section_page_id(section_key: str) -> str:
    return f"{SECTION_PAGE_ID_PREFIX}{section_key}"


def class_diagram_page_id() -> str:
    return CLASS_DIAGRAM_PAGE_ID


def class_diagram_output_paths() -> tuple[str, str]:
    return CLASS_DIAGRAM_OUTPUT_MARKDOWN, CLASS_DIAGRAM_OUTPUT_HTML


def sequence_diagram_page_id(key: str) -> str:
    return f"{SEQUENCE_DIAGRAM_PAGE_ID_PREFIX}{key}"


def use_case_diagram_page_id() -> str:
    return USE_CASE_DIAGRAM_PAGE_ID


def use_case_diagram_output_paths() -> tuple[str, str]:
    return USE_CASE_DIAGRAM_OUTPUT_MARKDOWN, USE_CASE_DIAGRAM_OUTPUT_HTML


def diagrams_index_page_id() -> str:
    return DIAGRAMS_INDEX_PAGE_ID


def diagrams_index_output_paths() -> tuple[str, str]:
    return DIAGRAMS_INDEX_OUTPUT_MARKDOWN, DIAGRAMS_INDEX_OUTPUT_HTML


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()
    return slug or "page"


def page_slug(name: str, entity_id: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9]+", "", entity_id)[-8:] or "0"
    return f"{slugify(name)}-{suffix}"


def module_output_paths(slug: str) -> tuple[str, str]:
    return f"modules/{slug}.md", f"modules/{slug}.html"


def diagram_output_paths(slug: str) -> tuple[str, str]:
    return f"diagrams/{slug}.md", f"diagrams/{slug}.html"


def section_slug(directory_path: str, section_key: str) -> str:
    """A readable, stable file name for a section page.

    Built from the section's directory rather than its title: a title can be
    rewritten by the narrator between runs, and keying the output file on it
    would orphan the previous file and break every link pointing at it. The
    hashed suffix disambiguates two sections carved out of the same directory,
    which `page_slug`'s "last 8 characters of the id" rule cannot do for keys
    that are paths.
    """
    base = slugify(directory_path) if directory_path not in ("", ".") else "root"
    suffix = hashlib.sha1(section_key.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


def section_output_paths(slug: str) -> tuple[str, str]:
    return f"sections/{slug}.md", f"sections/{slug}.html"


def relative_output_link(*, from_output_path: str, to_output_path: str, anchor: str | None = None) -> str:
    from_dir = PurePosixPath(from_output_path).parent
    to_path = PurePosixPath(to_output_path)
    relative = _relative_posix_path(from_dir, to_path)
    return f"{relative}#{anchor}" if anchor else relative


def relative_markdown_link(*, from_output_path_markdown: str, to_output_path_markdown: str, anchor: str | None = None) -> str:
    return relative_output_link(
        from_output_path=from_output_path_markdown,
        to_output_path=to_output_path_markdown,
        anchor=anchor,
    )


def _relative_posix_path(from_dir: PurePosixPath, to_path: PurePosixPath) -> str:
    from_parts = from_dir.parts
    to_parts = to_path.parts
    common = 0
    for left, right in zip(from_parts, to_parts):
        if left != right:
            break
        common += 1
    up = [".."] * (len(from_parts) - common)
    down = list(to_parts[common:])
    parts = up + down
    return "/".join(parts) if parts else to_path.name


def build_page_link(
    *,
    from_page_id: str,
    from_output_path_markdown: str,
    to_page_id: str,
    to_output_path_markdown: str,
    label: str,
    anchor: str | None = None,
) -> PageLink | None:
    if to_page_id == from_page_id:
        return None
    relative = relative_markdown_link(
        from_output_path_markdown=from_output_path_markdown,
        to_output_path_markdown=to_output_path_markdown,
        anchor=anchor,
    )
    return PageLink(fromPageId=from_page_id, toPageId=to_page_id, label=label, relativePath=relative)