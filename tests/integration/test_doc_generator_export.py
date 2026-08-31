from __future__ import annotations

import pytest

from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.writer import OutputRootEscapeError

from ._doc_generator_support import build_indexed_repo


def _build_generator(tmp_path, root, store, graph, output_root):
    manifest_store = open_doc_manifest_store(tmp_path / "repo.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=output_root,
        repositoryRoot=root,
    )


def test_generated_files_live_only_under_output_root_and_source_is_untouched(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    output_root = root / "docs"

    source_snapshot = {
        path: path.read_text(encoding="utf-8") for path in root.glob("*.py")
    }

    generator = _build_generator(tmp_path, root, store, graph, output_root)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in doc_set.pages:
        markdown_path = (output_root / page.outputPathMarkdown).resolve()
        html_path = (output_root / page.outputPathHtml).resolve()
        assert output_root.resolve() in markdown_path.parents
        assert output_root.resolve() in html_path.parents

    for path, original_content in source_snapshot.items():
        assert path.read_text(encoding="utf-8") == original_content


def test_manually_added_file_in_output_root_survives_regeneration(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    output_root = root / "docs"
    generator = _build_generator(tmp_path, root, store, graph, output_root)
    generator.generateRepositoryDocumentation(root, incremental=False)

    manual_file = output_root / "NOTES.md"
    manual_file.write_text("hand-written notes", encoding="utf-8")

    generator.generateRepositoryDocumentation(root, incremental=False)

    assert manual_file.read_text(encoding="utf-8") == "hand-written notes"


def test_writer_refuses_to_write_outside_output_root(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    output_root = root / "docs"
    generator = _build_generator(tmp_path, root, store, graph, output_root)

    with pytest.raises(OutputRootEscapeError):
        generator._writer._resolve_managed_path("../escape.md")


def test_output_root_cannot_overlap_analyzed_source(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, output_root=root)

    with pytest.raises(ValueError):
        generator.generateRepositoryDocumentation(root, incremental=False)


# ---------------------------------------------------------------------------
# The write path, counted in connections rather than seconds.
#
# The manifest store carried the same defect as the vector index and the
# metadata store: a connection opened, the schema replayed, one row written,
# committed and closed - once per page of the wiki. Counting connections is
# what makes it stay fixed.
# ---------------------------------------------------------------------------


def _count_manifest_connections(monkeypatch) -> list[object]:
    import doc_generator.manifest_store as manifest_module

    opened: list[object] = []
    real_connect = manifest_module._connect

    def counting_connect(db_path, **kwargs):
        opened.append(db_path)
        return real_connect(db_path, **kwargs)

    monkeypatch.setattr(manifest_module, "_connect", counting_connect)
    return opened


def test_generating_the_wiki_opens_one_manifest_connection(tmp_path, monkeypatch):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph, root / "docs")
    opened = _count_manifest_connections(monkeypatch)

    documentation = generator.generateRepositoryDocumentation(root, incremental=False)

    assert len(documentation.pages) > 3, "the run really did write several pages"
    assert len(opened) == 1, (
        f"one connection for the pass, not one per page: {len(opened)} opened "
        f"for {len(documentation.pages)} pages"
    )


def test_outside_a_session_a_manifest_call_still_opens_its_own_connection(tmp_path, monkeypatch):
    """The fallback stays intact: no caller is required to open a session."""
    manifest_store = open_doc_manifest_store(tmp_path / "solo.sqlite")
    opened = _count_manifest_connections(monkeypatch)

    manifest_store.load_entry("nothing")
    manifest_store.load_entry("nothing either")

    assert len(opened) == 2
