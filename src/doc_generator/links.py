from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import PageLink

HOME_PAGE_ID = "home"
HOME_OUTPUT_MARKDOWN = "index.md"
HOME_OUTPUT_HTML = "index.html"


def module_page_id(module_id: str) -> str:
    return f"module:{module_id}"


def diagram_page_id(module_id: str) -> str:
    return f"diagram:{module_id}"


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