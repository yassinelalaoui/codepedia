"""Neutralize raw HTML carried through Markdown into the generated wiki.

python-markdown passes raw HTML through by design, and `layout.html.jinja`
inserts the result with `| safe`. The Markdown reaching that point is not
authored by us: it is built from docstrings read out of the repository being
documented and from summaries written by an LLM. A docstring containing
`<script>` therefore became executable JavaScript on the same origin as the
chat API. Indexing `.md` files widens that from "a booby-trapped docstring" to
"an ordinary README", because raw HTML is idiomatic there - badges, `<details>`,
`<img>`.

The sanitizing happens on `md.htmlStash.rawHtmlBlocks` rather than on the final
HTML string, which is what makes it precise: the stash holds *only* the raw
fragments the author wrote, already separated from the markup python-markdown
generates itself. A pass over the serialized page could not tell the two apart,
and a regex over it would eventually corrupt a Mermaid diagram or a code
sample - the same reasoning that made `cross_references` a treeprocessor.

Two properties of the stash shape the parser below:

* Inline tags are stashed **individually and unbalanced** - `<em>text</em>`
  arrives as `<em>` in one entry and `</em>` in another, with `text` left as
  ordinary Markdown outside the stash. So each fragment is sanitized on its own
  and no open/close balancing is attempted; a rejected start tag and its
  rejected end tag are escaped independently by the same rule, which keeps the
  result consistent.
* Block-level HTML is stashed whole, so a `<details>...</details>` block is one
  entry and is parsed as a unit.

Anything outside the allowlist is **escaped, not dropped**: the reader sees the
markup that was refused instead of a silent hole, which is the same posture
`cross_references` takes when it declines to resolve a symbol.

The stash is only half the surface. Two Markdown constructions become HTML
*without ever being raw HTML*, so they never reach the stash at all:

* `attr_list` - enabled to pin symbol anchors - applies whatever attribute an
  author writes in `{: ... }`, event handlers included;
* an ordinary Markdown link or image accepts any URL scheme, `javascript:`
  included.

`sanitize_element_tree` therefore makes a second pass, over the element tree
python-markdown has finished building. That pass filters **attributes only** and
never touches a tag: by then the tree is the markup *we* generated from the
templates, and the author's own tags have already been judged in the stash.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

# Tags a repository's prose legitimately uses. Deliberately small: this is the
# set a README or a docstring needs, not a general-purpose HTML subset.
ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "code", "del", "details",
        "dd", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3",
        "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li", "ol", "p", "pre",
        "q", "s", "samp", "small", "span", "strong", "sub", "summary", "sup",
        "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "var",
    }
)

# Attributes allowed on every permitted tag.
ALLOWED_GLOBAL_ATTRIBUTES = frozenset({"class", "id", "title", "dir", "lang"})

# Attributes allowed only on specific tags, so `src` cannot appear on an
# arbitrary element.
ALLOWED_TAG_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "name", "target", "rel"}),
    "img": frozenset({"src", "alt", "width", "height", "align"}),
    "ol": frozenset({"start", "type"}),
    "td": frozenset({"colspan", "rowspan", "align", "valign"}),
    "th": frozenset({"colspan", "rowspan", "align", "valign", "scope"}),
    "table": frozenset({"align"}),
    "details": frozenset({"open"}),
    "del": frozenset({"datetime"}),
    "ins": frozenset({"datetime"}),
    # `module.md.jinja` stamps the symbol's opaque id onto its heading, next to
    # the readable anchor a reader sees in the URL bar. Headings only, and not
    # in the global set: an attribute a documented repository can also write
    # from a docstring should reach as few elements as possible, and this one
    # means nothing anywhere else. Nothing acts on it - it is a key the chat
    # panel can match a citation against without parsing the anchor text.
    **{tag: frozenset({"data-symbol-id"}) for tag in ("h1", "h2", "h3", "h4", "h5", "h6")},
}

# Attributes whose value is a URL and therefore needs its scheme checked.
URL_ATTRIBUTES = frozenset({"href", "src"})

# Relative URLs carry no scheme and are always allowed; these are the absolute
# forms a wiki page has a legitimate reason to reach. `data:` is deliberately
# absent - an inline image is not worth the payload surface it opens.
SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto"})

VOID_TAGS = frozenset({"br", "hr", "img"})

# `style` is not in any allowlist above and stays out of the raw-HTML one: an
# author has no reason to write it. The tree pass needs a narrow exception,
# because the `tables` extension renders column alignment as an inline style and
# nothing else python-markdown generates carries an attribute outside the sets
# above. Only `td`/`th`, and only this exact shape.
STYLE_ALLOWED_TAGS = frozenset({"td", "th"})
_TABLE_ALIGN_STYLE_PATTERN = re.compile(r"^text-align:\s*(?:left|right|center);?$", re.IGNORECASE)

# A scheme is letters/digits/+/-/. before the first colon, and only counts as a
# scheme when that colon comes before any path, query or fragment separator.
_SCHEME_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")

# Stripped before the scheme check: control characters and whitespace are the
# classic way to smuggle `java&#9;script:` past a naive prefix test. HTMLParser
# has already resolved entities in attribute values by this point, so
# `javascript&#58;...` arrives here as plain `javascript:`.
_URL_NOISE_PATTERN = re.compile(r"[\x00-\x20\x7f]")


def is_safe_url(value: str) -> bool:
    """True when `value` is relative, or absolute with an allowed scheme."""
    cleaned = _URL_NOISE_PATTERN.sub("", value)
    match = _SCHEME_PATTERN.match(cleaned)
    if match is None:
        return True
    return match.group(1).lower() in SAFE_URL_SCHEMES


def _attribute_allowed(tag: str, attribute: str) -> bool:
    if attribute.startswith("on"):
        # Every event handler, without needing to enumerate them.
        return False
    if attribute in ALLOWED_GLOBAL_ATTRIBUTES:
        return True
    return attribute in ALLOWED_TAG_ATTRIBUTES.get(tag, frozenset())


def _style_allowed(tag: str, value: str) -> bool:
    """True only for the column alignment `tables` emits on a cell."""
    return tag in STYLE_ALLOWED_TAGS and _TABLE_ALIGN_STYLE_PATTERN.match(value.strip()) is not None


def sanitize_element_tree(root) -> None:  # noqa: ANN001 - ElementTree's Element
    """Drop every disallowed attribute from a finished element tree, in place.

    The counterpart to `sanitize_fragment`, for the constructions that never
    become raw HTML: `attr_list`'s `{: onclick="..." }` and a Markdown
    `[link](javascript:...)` or `![image](javascript:...)`.

    Attributes only. The tags here were produced by python-markdown from our own
    templates, so removing one would be a rendering bug, not a defence - the
    author's tags were already sorted by the stash pass. A refused attribute is
    *removed* rather than escaped, unlike a refused tag: an attribute has no
    visible form to show the reader in its place. A refused `href`/`src` leaves
    the link text and the `alt` behind, exactly as `_emit_tag` already does.
    """
    for element in root.iter():
        tag = element.tag
        if not isinstance(tag, str):
            # Comments and processing instructions carry a callable tag.
            continue
        for name, value in tuple(element.attrib.items()):
            attribute = name.lower()
            if attribute == "style":
                if not _style_allowed(tag, value):
                    del element.attrib[name]
                continue
            if not _attribute_allowed(tag, attribute):
                del element.attrib[name]
                continue
            if attribute in URL_ATTRIBUTES and not is_safe_url(value):
                del element.attrib[name]


class _FragmentSanitizer(HTMLParser):
    """Rewrites one stashed fragment, escaping whatever is not allowed."""

    def __init__(self) -> None:
        # convert_charrefs=True resolves entities in both data and attribute
        # values before we see them, so an obfuscated `javascript&#58;` is
        # already decoded when `is_safe_url` checks it.
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    @property
    def result(self) -> str:
        return "".join(self._parts)

    def _emit_escaped_source(self) -> None:
        """Render the tag currently being handled as visible text."""
        self._parts.append(html.escape(self.get_starttag_text() or "", quote=False))

    def _emit_tag(self, tag: str, attrs, *, self_closing: bool) -> None:
        rendered = [tag]
        for name, value in attrs:
            attribute = name.lower()
            if not _attribute_allowed(tag, attribute):
                continue
            if value is None:
                rendered.append(attribute)
                continue
            if attribute in URL_ATTRIBUTES and not is_safe_url(value):
                continue
            rendered.append(attribute + '="' + html.escape(value, quote=True) + '"')
        closing = " />" if self_closing or tag in VOID_TAGS else ">"
        self._parts.append("<" + " ".join(rendered) + closing)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in ALLOWED_TAGS:
            self._emit_escaped_source()
            return
        self._emit_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag not in ALLOWED_TAGS:
            self._emit_escaped_source()
            return
        self._emit_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_TAGS:
            self._parts.append(html.escape("</" + tag + ">", quote=False))
            return
        if tag in VOID_TAGS:
            # Already self-closed by `_emit_tag`; a stray `</br>` would only
            # produce invalid markup.
            return
        self._parts.append("</" + tag + ">")

    def handle_data(self, data: str) -> None:
        self._parts.append(html.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        # Dropped rather than escaped: a comment is invisible today, and
        # printing it would make sanitizing look like a rendering bug. It is
        # also the historical vector for conditional-comment tricks.
        return

    def handle_decl(self, decl: str) -> None:
        self._parts.append(html.escape("<!" + decl + ">", quote=False))

    def unknown_decl(self, data: str) -> None:
        self._parts.append(html.escape("<![" + data + "]>", quote=False))

    def handle_pi(self, data: str) -> None:
        self._parts.append(html.escape("<?" + data + ">", quote=False))


def sanitize_fragment(fragment: str) -> str:
    """Sanitize one raw-HTML fragment. Safe on an unbalanced inline tag."""
    parser = _FragmentSanitizer()
    parser.feed(fragment)
    parser.close()
    return parser.result


# Runs last among treeprocessors: the stash is filled during block and inline
# parsing, and is only consumed later by the `raw_html` postprocessor, so any
# low priority works. 1 keeps it after `attr_list` (8), `toc` (5) and
# `codepedia_symbol_references` (15) rather than depending on their internals -
# which is also what makes the tree pass correct, since `attr_list` must have
# applied every `{: ... }` before the attributes are judged.
_TREEPROCESSOR_PRIORITY = 1


class SanitizeRawHtmlTreeprocessor(Treeprocessor):
    def run(self, root):  # noqa: ANN001 - python-markdown's API
        sanitize_element_tree(root)
        stash = getattr(self.md, "htmlStash", None)
        if stash is None:
            return root
        stash.rawHtmlBlocks = [sanitize_fragment(str(block)) for block in stash.rawHtmlBlocks]
        return root


class SanitizeRawHtmlExtension(Extension):
    def extendMarkdown(self, md) -> None:  # noqa: N802 - python-markdown's API
        md.treeprocessors.register(
            SanitizeRawHtmlTreeprocessor(md),
            "codepedia_sanitize_raw_html",
            _TREEPROCESSOR_PRIORITY,
        )
