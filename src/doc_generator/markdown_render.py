from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Symbol/module names routinely contain markdown-special characters that
# were never meant to be markdown syntax - most commonly `_` (e.g.
# `__init__`, `sqlite_store`), which python-markdown's classic emphasis
# processor can pair up across an *entire* list/paragraph block rather than
# per-word, silently swallowing an unrelated link or bolding a large stray
# span. Any name used as markdown link text or inline label (not full prose
# like a docstring/summary, which is meant to render as markdown) must be
# escaped with this filter before being embedded in a template.
_MARKDOWN_SPECIAL_CHARS = re.compile(r"([\\`*_{}\[\]()#+\-.!<>|~])")


def _markdown_escape(value: object) -> str:
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", str(value))


_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html.jinja",), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
)
_environment.filters["mdesc"] = _markdown_escape


def template_fingerprint() -> str:
    """Identifies the templates that produced the current output.

    Every page's Markdown and its surrounding HTML shell are rendered from these
    files, so editing one makes every already-written page stale - and nothing
    else notices. `impact.compute_regeneration_impact` reasons about *source*
    changes: a template is not a source file, carries no symbol, and appears in
    no dependency edge, so a template edit produced an impact set of exactly
    nothing while changing what every page should contain.

    The observable symptom was a wiki where some pages had the new shell and some
    the old, depending only on which source files happened to change afterwards.

    Both name and content are hashed, so adding or removing a template counts as
    a change too. Read fresh on each call rather than cached at import: `serve`
    holds one process across edits.
    """
    digest = hashlib.sha1()
    for path in sorted(TEMPLATES_DIR.glob("*.jinja")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def render_markdown_template(template_name: str, **context: Any) -> str:
    template = _environment.get_template(template_name)
    return template.render(**context)


def render_html_template(template_name: str, **context: Any) -> str:
    template = _environment.get_template(template_name)
    return template.render(**context)