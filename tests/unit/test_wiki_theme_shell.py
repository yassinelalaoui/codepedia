"""The page shell's theme plumbing (036 contracts/wiki-theme-shell.md).

These cover what the generator emits. The behaviour that depends on a real
browser - that the theme is applied before first paint, and that two wikis on
the shared `file://` origin cannot overwrite each other - is verified over CDP
instead (quickstart.md §4), because jsdom has no paint and does not model
`file://` origins.
"""

from __future__ import annotations

import re

from doc_generator.html_render import render_page_html, wiki_id

PAGE_KINDS = (
    "index.html",
    "modules/example.html",
    "diagrams/example-diagram.html",
)

SIMPLE_PAGE = "# title\n\nSome prose.\n"


def _render(output_path_html: str, repository_id: str = "repo::/tmp/alpha") -> str:
    return render_page_html(
        title="fixture",
        content_markdown=SIMPLE_PAGE,
        output_path_html=output_path_html,
        repository_id=repository_id,
    )


def _head_of(html: str) -> str:
    return html.split("</head>", 1)[0]


def test_every_page_kind_carries_the_theme_script_in_head():
    for output_path_html in PAGE_KINDS:
        head = _head_of(_render(output_path_html))
        assert "codepedia:theme:" in head, output_path_html


def test_theme_script_is_inline_and_not_deferred():
    """A deferred or external script runs after first paint, which is the whole
    defect FR-008 exists to prevent."""
    html = _render("index.html")
    head = _head_of(html)
    theme_script = re.search(r"<script>(?:(?!</script>).)*codepedia:theme:.*?</script>", head, re.S)
    assert theme_script is not None
    opening = theme_script.group(0)[: theme_script.group(0).index(">") + 1]
    assert "src=" not in opening
    assert "defer" not in opening
    assert "async" not in opening


def test_theme_script_runs_before_any_body_content():
    # Anchored on </head> rather than on "<body>": the script's own explanatory
    # comment contains the text "<body>", and matching that instead of the tag
    # is how this assertion silently passes while testing nothing.
    html = _render("index.html")
    assert html.index("codepedia:theme:") < html.index("</head>")


def test_theme_script_precedes_the_stylesheet_and_the_bundle():
    """Order matters more than presence: the attribute has to be on <html>
    before the browser has anything to paint with."""
    html = _render("index.html")
    # Real tags only, for the same reason as above - the comment names both
    # files in prose well before either is actually loaded.
    assert html.index("codepedia:theme:") < html.index('<link rel="stylesheet"')
    assert html.index("codepedia:theme:") < html.index('<script src="assets/wiki-ui.js">')


def test_every_page_kind_has_the_theme_control_mount_point():
    for output_path_html in PAGE_KINDS:
        assert 'id="wiki-theme-root"' in _render(output_path_html), output_path_html


def test_theme_script_never_writes_the_system_sentinel():
    """System is the *absence* of the attribute. A `data-theme="system"` value
    would satisfy the stylesheet's :not([data-theme="light"]) dark guard while
    matching no dark rule either - a state the CSS cannot express."""
    html = _render("index.html")
    assert 'data-theme", "system"' not in html
    assert "'data-theme', 'system'" not in html


def test_theme_script_only_stamps_a_pinned_choice():
    html = _render("index.html")
    head = _head_of(html)
    assert "'light'" in head and "'dark'" in head


def test_two_repositories_get_different_wiki_ids():
    alpha = _render("index.html", repository_id="repo::/tmp/alpha")
    beta = _render("index.html", repository_id="repo::/tmp/beta")
    assert _storage_key(alpha) != _storage_key(beta)


def test_the_same_repository_gets_a_stable_wiki_id_across_renders():
    first = _render("index.html", repository_id="repo::/tmp/alpha")
    second = _render("index.html", repository_id="repo::/tmp/alpha")
    assert _storage_key(first) == _storage_key(second)


def test_every_page_of_one_wiki_shares_one_key():
    keys = {_storage_key(_render(path)) for path in PAGE_KINDS}
    assert len(keys) == 1


def test_the_wiki_id_is_a_hash_not_the_repository_path():
    """The repository id is `repo::/abs/posix/path`. Emitting it raw would put
    the author's directory layout into every page of a shareable artifact."""
    html = _render("index.html", repository_id="repo::/home/someone/secret-project")
    assert "secret-project" not in html
    assert "/home/someone" not in html
    assert wiki_id("repo::/home/someone/secret-project") in html


def _storage_key(html: str) -> str:
    match = re.search(r'wikiId: "([0-9a-f]{16})"', html)
    assert match is not None, "no wiki id in the rendered page"
    return match.group(1)
