"""Turn symbol and file mentions in generated prose into wiki links.

The LLM-written summaries name classes, functions and files in backticks
(``repository_metadata/summary_prompts.py`` asks for exactly that). This module
resolves those mentions against the same symbol manifest the client-side search
widget already consumes (``search_index.py``) and rewrites them as links.

It runs as a python-markdown ``Treeprocessor`` rather than a regex pass over the
rendered HTML, for two reasons that both matter here:

* It sees the element tree *after* inline processing, so an inline ``<code>``
  span is structurally distinguishable from a fenced ``<pre><code>`` block. A
  regex over HTML cannot make that distinction reliably, and would eventually
  corrupt a Mermaid diagram source or a code sample by injecting an anchor.
* It only ever touches ``DocPage.renderedHtml``; ``DocPage.contentMarkdown`` is
  left alone, so the ``.md`` artifacts written to disk never churn when the
  symbol manifest changes. That also keeps ``contracts/doc-generator.md``'s
  invariant intact - the HTML stays *derived from* the Markdown rather than
  authored separately.

Resolution deliberately refuses to guess: a mention that is ambiguous and not
disambiguated by the page's own module is left as plain code. A wrong link costs
more reader trust than a missing one - the same posture
``frontend/src/lib/markdownReferences.tsx`` already takes in the chat panel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree.ElementTree import Element

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from .links import relative_output_link
from .search_index import SearchIndexDocument, SearchIndexEntry

REFERENCE_SEPARATOR = " :: "

# Anything longer, or spanning lines, is a code sample rather than a mention.
_MAX_REFERENCE_LENGTH = 120

# Runs after python-markdown's `inline` treeprocessor (priority 20), which is
# what creates the `<code>` elements this pass rewrites.
_TREEPROCESSOR_PRIORITY = 15


@dataclass(frozen=True, slots=True)
class SymbolLookup:
    """Name/path/id indexes over a ``SearchIndexDocument``, built once per run."""

    byName: dict[str, tuple[SearchIndexEntry, ...]]
    byFilePath: dict[str, SearchIndexEntry]
    bySymbolId: dict[str, SearchIndexEntry]


def build_symbol_lookup(search_index: SearchIndexDocument) -> SymbolLookup:
    by_name: dict[str, list[SearchIndexEntry]] = {}
    by_file_path: dict[str, SearchIndexEntry] = {}
    by_symbol_id: dict[str, SearchIndexEntry] = {}
    for entry in search_index.entries:
        by_name.setdefault(entry.name, []).append(entry)
        by_symbol_id.setdefault(entry.symbolId, entry)
        if entry.kind == "module":
            by_file_path.setdefault(_normalize_path(entry.filePath), entry)
    return SymbolLookup(
        byName={name: tuple(entries) for name, entries in by_name.items()},
        byFilePath=by_file_path,
        bySymbolId=by_symbol_id,
    )


def resolve_reference(
    lookup: SymbolLookup, text: str, *, current_file_path: str = ""
) -> SearchIndexEntry | None:
    """Resolve one inline mention, or return None when it must stay plain code.

    Order: the explicit ``path :: Symbol`` form the chat panel already uses, then
    a file path, then a qualified ``Class.method`` name, then a bare name. A bare
    name only resolves when the page's own module claims it, or when exactly one
    symbol in the whole repository carries it.
    """
    candidate = text.strip()
    if not candidate or len(candidate) > _MAX_REFERENCE_LENGTH or "\n" in candidate:
        return None

    if REFERENCE_SEPARATOR in candidate:
        file_path, _, symbol_id = candidate.partition(REFERENCE_SEPARATOR)
        entry = lookup.bySymbolId.get(symbol_id.strip())
        if entry is not None:
            return entry
        return lookup.byFilePath.get(_normalize_path(file_path.strip()))

    path_entry = _resolve_path(lookup, candidate)
    if path_entry is not None:
        return path_entry

    matches = lookup.byName.get(candidate)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    current = _normalize_path(current_file_path)
    owned = [entry for entry in matches if _normalize_path(entry.filePath) == current]
    return owned[0] if len(owned) == 1 else None


def build_reference_href(entry: SearchIndexEntry, *, output_path_html: str) -> str:
    """Wiki link for ``entry``, relative to the page currently being rendered.

    A target on the current page becomes a bare ``#anchor`` fragment;
    ``relative_output_link`` would return the page's own filename for a
    self-link, which works but needlessly reloads the page.
    """
    page_path, _, anchor = entry.pageUrl.partition("#")
    if _normalize_path(page_path) == _normalize_path(output_path_html):
        return f"#{anchor}" if anchor else ""
    return relative_output_link(
        from_output_path=output_path_html,
        to_output_path=page_path,
        anchor=anchor or None,
    )


class SymbolReferenceTreeprocessor(Treeprocessor):
    def __init__(
        self, md, *, lookup: SymbolLookup, output_path_html: str, current_file_path: str
    ) -> None:
        super().__init__(md)
        self._lookup = lookup
        self._output_path_html = output_path_html
        self._current_file_path = current_file_path

    def run(self, root: Element) -> None:
        # Collected first, rewritten second: replacing a child in place while
        # `root.iter()` is still walking would hand the walker the new anchor and
        # re-visit the `<code>` it now wraps.
        targets: list[tuple[Element, int, Element]] = []
        for parent in root.iter():
            if parent.tag == "pre":
                continue
            for index, child in enumerate(parent):
                if child.tag == "code" and child.text:
                    targets.append((parent, index, child))

        for parent, index, code in targets:
            entry = resolve_reference(
                self._lookup, code.text or "", current_file_path=self._current_file_path
            )
            if entry is None:
                continue
            href = build_reference_href(entry, output_path_html=self._output_path_html)
            if not href:
                continue
            anchor = Element("a", {"href": href, "class": "symbol-ref"})
            anchor.tail = code.tail
            code.tail = None
            anchor.append(code)
            parent[index] = anchor


class SymbolReferenceExtension(Extension):
    def __init__(
        self, *, lookup: SymbolLookup, output_path_html: str, current_file_path: str = ""
    ) -> None:
        super().__init__()
        self._lookup = lookup
        self._output_path_html = output_path_html
        self._current_file_path = current_file_path

    def extendMarkdown(self, md) -> None:  # noqa: N802 - python-markdown's API
        md.treeprocessors.register(
            SymbolReferenceTreeprocessor(
                md,
                lookup=self._lookup,
                output_path_html=self._output_path_html,
                current_file_path=self._current_file_path,
            ),
            "codepedia_symbol_references",
            _TREEPROCESSOR_PRIORITY,
        )


def _resolve_path(lookup: SymbolLookup, candidate: str) -> SearchIndexEntry | None:
    """Match a file mention, tolerating a repository-relative form.

    Stored module paths can be absolute (they come from the scanner), while a
    summary naturally writes ``src/pkg/mod.py``, so a suffix match on whole path
    segments is accepted as well as an exact one.
    """
    normalized = _normalize_path(candidate)
    if not normalized or ("/" not in normalized and "." not in normalized):
        return None
    exact = lookup.byFilePath.get(normalized)
    if exact is not None:
        return exact
    suffix = f"/{normalized}"
    matches = [entry for path, entry in lookup.byFilePath.items() if path.endswith(suffix)]
    return matches[0] if len(matches) == 1 else None


def _normalize_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix() if path else ""
