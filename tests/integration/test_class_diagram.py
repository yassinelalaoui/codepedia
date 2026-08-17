from __future__ import annotations

from pathlib import Path

from dependency_graph import DependencyGraph
from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.class_diagram import ClassDiagramSelection, SelectedClass, SelectedMethod
from doc_generator.markdown_render import render_markdown_template
from doc_generator.mermaid_diagram import build_class_diagram_mermaid_source
from parser_engine import SourceFile, extract_symbols
from repository_metadata import RepositoryMetadataStore, compute_content_hash

from ._doc_generator_support import build_indexed_repo


def _build_generator(tmp_path: Path, root: Path, store, graph) -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / "repo.sqlite")
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def test_class_diagram_shows_cross_module_inheritance(tmp_path):
    """alpha/beta/gamma fixture: Child (beta.py) inherits BaseThing (gamma.py)."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    class_diagram_page = next(page for page in doc_set.pages if page.kind == "class-diagram")
    assert "Child" in class_diagram_page.contentMarkdown
    assert "BaseThing" in class_diagram_page.contentMarkdown
    assert "<|--" in class_diagram_page.contentMarkdown

    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert class_diagram_page.outputPathMarkdown in home_page.contentMarkdown


def _build_zero_class_repo(tmp_path: Path):
    root = tmp_path / "no-classes-repo"
    root.mkdir()
    module_path = root / "only_funcs.py"
    module_path.write_text('"""Only functions."""\n\n\ndef helper() -> int:\n    return 1\n', encoding="utf-8")

    inventory = extract_symbols(SourceFile(path=module_path, language="python"))
    graph = DependencyGraph.build_from_inventories([inventory], sourceFile=str(root))

    store = RepositoryMetadataStore(tmp_path / "no-classes-repo.sqlite")
    store.ensure_repository(root, detected_languages=("python",))
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=module_path, language="python"),
        inventory=inventory,
        content_hash=compute_content_hash(module_path),
    )
    return root, store, graph


def test_no_class_diagram_page_when_repository_has_zero_classes(tmp_path):
    root, store, graph = _build_zero_class_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)

    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    assert all(page.kind != "class-diagram" for page in doc_set.pages)
    home_page = next(page for page in doc_set.pages if page.kind == "home")
    assert "class-overview" not in home_page.contentMarkdown


def test_class_diagram_regenerates_on_incremental_run_after_unrelated_change(tmp_path):
    """The class diagram is repository-wide, so per research.md Decision 3 it
    always refreshes on any qualifying change - not just when a change directly
    touches Child/BaseThing themselves."""
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    alpha_path = root / "alpha.py"
    alpha_path.write_text(
        alpha_path.read_text(encoding="utf-8").replace("return beta_helper(value)", "return beta_helper(value) + 0"),
        encoding="utf-8",
    )
    alpha_inventory = extract_symbols(SourceFile(path=alpha_path, language="python"))
    graph.ingest_inventory(alpha_inventory)
    store.store_inventory(
        repository_root=root,
        source_file=SourceFile(path=alpha_path, language="python"),
        inventory=alpha_inventory,
        content_hash=compute_content_hash(alpha_path),
    )

    doc_set = generator.generateRepositoryDocumentation(root, incremental=True, changedPaths=[str(alpha_path)])

    regenerated_kinds = {page.kind for page in doc_set.pages}
    assert "class-diagram" in regenerated_kinds


def test_class_diagram_mermaid_source_is_well_formed_with_a_sanitized_semicolon():
    """No supported source language allows a literal `;` inside an identifier,
    so this can't be exercised through a real parsed fixture file - it's
    tested at the same level T006 already does (a hand-built selection), but
    asserting the acceptance-level structural properties a real Mermaid
    parser requires: a `classDiagram` header, a declaration for every
    included class, and balanced braces - on top of T006's "no bare `;`"
    assertion, per quickstart.md "Validate the Mermaid parses" and Research
    Decision 4. (A real Mermaid parser was used interactively during
    planning/implementation of this feature to independently confirm
    comma-sanitized labels parse cleanly in both `classDiagram` and
    `sequenceDiagram` contexts; wiring a Node/mermaid dependency into this
    Python project's test suite for one defensive edge case was judged not
    worth the added infrastructure, per the constitution's "minimal
    infrastructure" principle.)"""
    selection = ClassDiagramSelection(
        includedClasses=(
            SelectedClass(classId="c1", name="Foo;Bar", methods=(SelectedMethod(name="do;It"),)),
        ),
        inheritanceEdges=(),
        omittedClassCount=0,
    )

    result = build_class_diagram_mermaid_source(selection)

    assert ";" not in result.sourceText
    assert result.sourceText.startswith("classDiagram")
    assert result.sourceText.count("{") == result.sourceText.count("}")
    assert 'class c0["Foo,Bar"]' in result.sourceText


def test_class_diagram_page_states_how_many_classes_were_omitted(tmp_path):
    """quickstart.md 'Validate the class diagram' step 4: a repository with
    more classes than the cap must state the omitted count on the page, not
    silently show a partial diagram."""
    selection = ClassDiagramSelection(
        includedClasses=tuple(SelectedClass(classId=f"c{i}", name=f"C{i}") for i in range(40)),
        inheritanceEdges=(),
        omittedClassCount=7,
    )
    class_diagram_source = build_class_diagram_mermaid_source(selection)

    content = render_markdown_template("class_diagram.md.jinja", class_diagram_source=class_diagram_source)

    assert "7 additional classes omitted for legibility" in content
    assert "```mermaid" in content
