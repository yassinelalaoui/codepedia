from __future__ import annotations

import json

import pytest

from repo_scanner.docs_scope import (
    DEFAULT_DOCS_INCLUDE,
    CONFIG_FILENAME,
    DocsScope,
    load_docs_scope,
)


def test_default_scope_covers_the_readme_and_a_documentation_directory():
    scope = DocsScope()

    assert scope.covers("README.md")
    assert scope.covers("docs/architecture.md")
    assert scope.covers("docs/diagrams/class-diagram.md")
    assert scope.covers("documentation/guide.md")


def test_default_scope_excludes_scaffolding_and_non_root_readmes():
    scope = DocsScope()

    # The finding that motivated the perimeter: 89% of this repository's
    # Markdown symbols came from `specs/`, which is generated scaffolding.
    assert not scope.covers("specs/003-feature/spec.md")
    assert not scope.covers(".specify/templates/plan-template.md")
    assert not scope.covers(".github/copilot-instructions.md")
    # A README that documents a build step, not the project.
    assert not scope.covers("packaging/README.md")
    # A vendored tree that happens to carry its own `docs/`: it documents
    # somebody else's project, and an unanchored `docs/` pattern would index all
    # 657 files of it. A monorepo declares its real layout in `.codepedia.json`.
    assert not scope.covers("vendor/other-project/docs/guide.md")


def test_exclude_is_applied_after_include():
    scope = DocsScope(include=("docs/",), exclude=("docs/generated/",))

    assert scope.covers("docs/stack.md")
    assert not scope.covers("docs/generated/api.md")


def test_backslash_paths_are_normalized():
    assert DocsScope().covers(r"docs\architecture.md")


def test_load_falls_back_to_defaults_when_no_config_file(tmp_path):
    assert load_docs_scope(tmp_path).include == DEFAULT_DOCS_INCLUDE


def test_load_reads_declared_patterns(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"docs": {"include": ["specs/**"], "exclude": ["specs/archive/**"]}}), encoding="utf-8"
    )

    scope = load_docs_scope(tmp_path)

    assert scope.covers("specs/003-feature/spec.md")
    assert not scope.covers("specs/archive/old.md")
    assert not scope.covers("README.md"), "a declared include replaces the defaults, it does not extend them"


def test_a_missing_key_keeps_that_half_of_the_default(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(json.dumps({"docs": {"exclude": ["docs/private/**"]}}), encoding="utf-8")

    scope = load_docs_scope(tmp_path)

    assert scope.covers("README.md")
    assert not scope.covers("docs/private/notes.md")


@pytest.mark.parametrize(
    "payload",
    ["{ not json", json.dumps(["docs"]), json.dumps({"docs": "docs/**"}), json.dumps({"docs": {"include": "docs/**"}})],
)
def test_a_malformed_config_fails_loudly_naming_the_file(tmp_path, payload):
    # Falling back to the defaults here would be indistinguishable from a config
    # that was never written, and the symptom - documentation missing from the
    # wiki - would only surface an indexing run later.
    (tmp_path / CONFIG_FILENAME).write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=CONFIG_FILENAME):
        load_docs_scope(tmp_path)
