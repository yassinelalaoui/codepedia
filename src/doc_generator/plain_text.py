"""Markdown in, one readable line of plain text out. No model, no dependency.

The Overview's module list printed a module's leading documentation verbatim.
For a code module that is a docstring and mostly harmless; for a README it is
the document's opening - heading hash, emphasis markers, a horizontal rule -
which `mdesc` then escaped into visible backslashes and the character budget
cut off mid-word. This reduces it to what a reader would say out loud, and
shortens it where a reader would: at the end of a sentence, or failing that at
a word, marked with an ellipsis.

Deliberately a reduction, not a renderer. Nothing here produces Markdown, so
the caller still escapes the result before it reaches a template.
"""

from __future__ import annotations

import re

# A module-list row holds one line; past this it wraps into the next row's
# space on a narrow window.
MAX_MODULE_DESCRIPTION_CHARS = 160

ELLIPSIS = "…"

_FENCE = re.compile(r"^\s*(```|~~~)")
_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}(\s+|$)")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_BLOCKQUOTE = re.compile(r"^\s*>\s?")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REFERENCE_LINK = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
# Single `*`/`_` emphasis, but never an underscore inside a word: `snake_case`
# is an identifier, not emphasis.
_EMPHASIS = re.compile(r"(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*])")
_CODE = re.compile(r"`+([^`]*)`+")
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|~])")
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def to_plain(text: str) -> str:
    """Strip Markdown structure and inline markers, collapsing to one line."""
    if not text:
        return ""
    kept: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        if _FENCE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence or _RULE.match(raw_line) or _ATX_HEADING.match(raw_line):
            continue
        line = _BLOCKQUOTE.sub("", raw_line)
        line = _LIST_MARKER.sub("", line)
        kept.append(line)

    plain = " ".join(kept)
    plain = _IMAGE.sub("", plain)
    plain = _LINK.sub(r"\1", plain)
    plain = _REFERENCE_LINK.sub(r"\1", plain)
    plain = _HTML_TAG.sub("", plain)
    plain = _CODE.sub(r"\1", plain)
    # A backtick with no partner - "`path` — text" cut to "path` — text" by
    # an earlier reader - is quoting nothing.
    plain = plain.replace("`", "")
    plain = _STRONG.sub(r"\2", plain)
    plain = _EMPHASIS.sub(r"\2", plain)
    plain = _ESCAPE.sub(r"\1", plain)
    plain = _WHITESPACE.sub(" ", plain).strip()
    # Punctuation orphaned by a removed tag or image ("a <br/> b" -> "a  b").
    return re.sub(r"\s+([,.;:!?])", r"\1", plain)


def excerpt(text: str, max_chars: int = MAX_MODULE_DESCRIPTION_CHARS) -> str:
    """`text` as plain prose, no longer than `max_chars`.

    Ends at the last sentence boundary that fits; otherwise at the last word
    boundary that fits, followed by an ellipsis. Never mid-word, except for a
    single word longer than the whole budget, which cannot be helped.
    """
    return _shorten(to_plain(text), max_chars)


def marked_excerpt(text: str, max_chars: int = MAX_MODULE_DESCRIPTION_CHARS) -> str:
    """`excerpt`, but a shortened result always says so (038 spec FR-032).

    `excerpt` marks only a cut at a word; one after a whole sentence reads as
    complete. For a module-list row, where the full text is a click away, the
    owner chose to mark both (038 research Decision 12). The mark's room is
    kept inside `max_chars`.
    """
    plain = to_plain(text)
    if len(plain) <= max_chars:
        return plain
    cut = _shorten(plain, max_chars - len(" " + ELLIPSIS))
    return cut if cut.endswith(ELLIPSIS) else f"{cut} {ELLIPSIS}"


def _shorten(plain: str, max_chars: int) -> str:
    if len(plain) <= max_chars:
        return plain

    window = plain[: max_chars + 1]
    sentence_ends = [match.end() for match in _SENTENCE_END.finditer(window) if match.end() <= max_chars]
    if sentence_ends:
        return plain[: sentence_ends[-1]]

    budget = max_chars - len(ELLIPSIS)
    cut = plain.rfind(" ", 0, budget + 1)
    if cut <= 0:
        return plain[:budget] + ELLIPSIS
    return plain[:cut].rstrip(" ,;:-") + ELLIPSIS


def first_sentence(text: str, max_chars: int) -> str:
    """The first sentence of `text` as plain prose, shortened like `excerpt`."""
    plain = to_plain(text)
    match = _SENTENCE_END.search(plain)
    sentence = plain[: match.end()] if match else plain
    return excerpt(sentence, max_chars=max_chars)
