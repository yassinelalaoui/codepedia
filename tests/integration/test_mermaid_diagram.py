from __future__ import annotations

import re
from pathlib import Path

from dependency_graph import DependencyGraph
from parser_engine import SourceFile, extract_symbols
from repository_metadata import DependencyEdge, RepositoryMetadataStore, compute_content_hash
from repository_metadata.sqlite_store import stable_repository_id, stable_source_file_id

from doc_generator import DocGenerator, open_doc_manifest_store
from doc_generator.writer import MERMAID_ASSET_OUTPUT_PATH

from ._doc_generator_support import build_indexed_repo

_CLICK_PATTERN = re.compile(r'click (\S+) href "([^"]+)"')
_NODE_PATTERN = re.compile(r'^\s*n\d+\[', re.MULTILINE)


def _build_generator(tmp_path: Path, root: Path, store, graph, *, db_name: str = "repo.sqlite") -> DocGenerator:
    manifest_store = open_doc_manifest_store(tmp_path / db_name)
    return DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=root / "docs",
        repositoryRoot=root,
    )


def _index_repo(tmp_path: Path, root: Path, file_paths: list[Path], db_name: str):
    inventories = [extract_symbols(SourceFile(path=path, language="python")) for path in file_paths]
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(root))
    repository_id = stable_repository_id(root)
    edges = [
        DependencyEdge(
            sourceId=edge.sourceId,
            targetId=edge.targetId,
            type=edge.type,
            sourceFileId=stable_source_file_id(repository_id, edge.sourceFile or root),
            metadata=dict(edge.metadata),
        )
        for edge in graph.edges.values()
    ]
    store = RepositoryMetadataStore(tmp_path / db_name)
    store.ensure_repository(root, detected_languages=("python",))
    for inventory in inventories:
        source_path = Path(inventory.sourceFile)
        store.store_inventory(
            repository_root=root,
            source_file=SourceFile(path=source_path, language="python"),
            inventory=inventory,
            dependency_edges=edges,
            content_hash=compute_content_hash(source_path),
        )
    return store, graph


def _build_chain_repo(tmp_path: Path, *, length: int):
    """A straight-line import chain mod0 -> mod1 -> ... -> mod{length-1}."""
    root = tmp_path / "chain-repo"
    root.mkdir()
    for index in range(length):
        lines = [f'"""Module {index}."""', ""]
        if index + 1 < length:
            lines.append(f"from mod{index + 1} import value{index + 1}")
            lines.append("")
        lines.append(f"def value{index}() -> int:")
        lines.append(f"    return {index}")
        (root / f"mod{index}.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    file_paths = [root / f"mod{index}.py" for index in range(length)]
    store, graph = _index_repo(tmp_path, root, file_paths, "chain-repo.sqlite")
    return root, store, graph


def _build_star_repo(tmp_path: Path, *, leaf_count: int):
    """One hub module that directly imports many leaf modules."""
    root = tmp_path / "star-repo"
    root.mkdir()
    hub_lines = ['"""Hub module."""', ""]
    for index in range(leaf_count):
        hub_lines.append(f"from leaf{index} import value{index}")
    hub_lines.append("")
    hub_lines.append("def use_all() -> int:")
    hub_lines.append("    return " + " + ".join(f"value{index}()" for index in range(leaf_count)))
    (root / "hub.py").write_text("\n".join(hub_lines) + "\n", encoding="utf-8")
    for index in range(leaf_count):
        (root / f"leaf{index}.py").write_text(
            f'"""Leaf {index}."""\n\ndef value{index}() -> int:\n    return {index}\n', encoding="utf-8"
        )
    file_paths = [root / "hub.py"] + [root / f"leaf{index}.py" for index in range(leaf_count)]
    store, graph = _index_repo(tmp_path, root, file_paths, "star-repo.sqlite")
    return root, store, graph


def test_diagram_click_hrefs_point_at_correct_module_pages(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    diagram_pages = [page for page in doc_set.pages if page.kind == "diagram"]
    assert diagram_pages, "expected at least one diagram page"

    for diagram_page in diagram_pages:
        clicks = dict(_CLICK_PATTERN.findall(diagram_page.contentMarkdown))
        # Every neighbor/owner PageLink should have a matching click href that is
        # the same relative path, just pointing at the .html counterpart.
        assert clicks, f"expected click directives on {diagram_page.id}"
        for link in diagram_page.links:
            expected_href = link.relativePath.replace(".md", ".html")
            matching_hrefs = [href for href in clicks.values() if href == expected_href]
            assert matching_hrefs, (
                f"no click directive on {diagram_page.id} matches PageLink to {link.toPageId} "
                f"(expected href {expected_href!r}, got {list(clicks.values())})"
            )


def test_diagram_scoped_to_direct_dependencies_in_a_large_chain(tmp_path):
    root, store, graph = _build_chain_repo(tmp_path, length=21)
    generator = _build_generator(tmp_path, root, store, graph, db_name="chain-repo.sqlite")
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    middle_diagram = next(page for page in doc_set.pages if page.kind == "diagram" and page.title.startswith("mod10"))
    node_count = len(_NODE_PATTERN.findall(middle_diagram.contentMarkdown))

    # mod10 only ever has mod9 (importer) and mod11 (imported) as direct neighbors,
    # plus itself - never the other 18 modules in the 21-module chain.
    assert node_count == 3, f"expected 3 nodes (self + 2 direct neighbors), got {node_count}"


def test_diagram_stays_well_formed_with_many_direct_dependencies(tmp_path):
    root, store, graph = _build_star_repo(tmp_path, leaf_count=30)
    generator = _build_generator(tmp_path, root, store, graph, db_name="star-repo.sqlite")
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    hub_diagram = next(page for page in doc_set.pages if page.kind == "diagram" and page.title.startswith("hub"))
    mermaid_block = hub_diagram.contentMarkdown.split("```mermaid")[1].split("```")[0]

    node_ids = set(re.findall(r'\bn(\d+)\[', mermaid_block))
    edge_matches = re.findall(r'\bn(\d+) -->\|import\| n(\d+)\b', mermaid_block)
    click_matches = _CLICK_PATTERN.findall(mermaid_block)

    assert len(node_ids) == 31, f"expected hub + 30 leaves = 31 nodes, got {len(node_ids)}"
    assert len(edge_matches) == 30, f"expected 30 import edges from hub, got {len(edge_matches)}"
    # Every referenced node id in an edge or click directive must be one we declared.
    for source_id, target_id in edge_matches:
        assert source_id in node_ids and target_id in node_ids
    for node_id, _href in click_matches:
        assert node_id in {f"n{value}" for value in node_ids}


def test_no_cdn_reference_and_classic_script_tag(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)

    for page in doc_set.pages:
        assert "http://" not in page.renderedHtml
        assert "https://" not in page.renderedHtml
        script_tags = re.findall(r"<script[^>]*>", page.renderedHtml)
        mermaid_script_tags = [tag for tag in script_tags if "mermaid" in tag]
        assert mermaid_script_tags, f"expected a mermaid script tag on {page.id}"
        for tag in mermaid_script_tags:
            assert 'type="module"' not in tag, f"mermaid script tag must not be a module script: {tag}"

    asset_path = root / "docs" / MERMAID_ASSET_OUTPUT_PATH
    assert asset_path.exists()


def test_mermaid_asset_is_not_rewritten_when_unchanged(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    generator = _build_generator(tmp_path, root, store, graph)
    generator.generateRepositoryDocumentation(root, incremental=False)

    asset_path = root / "docs" / MERMAID_ASSET_OUTPUT_PATH
    first_mtime = asset_path.stat().st_mtime_ns

    generator.generateRepositoryDocumentation(root, incremental=False)
    second_mtime = asset_path.stat().st_mtime_ns

    assert first_mtime == second_mtime, "asset should not be rewritten when its content is unchanged"
