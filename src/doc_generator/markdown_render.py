from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html.jinja",), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_markdown_template(template_name: str, **context: Any) -> str:
    template = _environment.get_template(template_name)
    return template.render(**context)


def render_html_template(template_name: str, **context: Any) -> str:
    template = _environment.get_template(template_name)
    return template.render(**context)