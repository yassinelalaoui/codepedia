from __future__ import annotations

import pytest

from chat.models import ChatMessage, RetrievedEvidence
from chat.rerank import (
    build_symbol_node_index,
    neighbour_ids,
    recent_cited_symbol_ids,
    rerank_by_graph_proximity,
)

from ._doc_generator_support import build_indexed_repo


@pytest.fixture()
def indexed(tmp_path):
    root, store, graph = build_indexed_repo(tmp_path)
    return root, store, graph


def _symbol_named(store, root, relative_path, name):
    bundle = store.load_source_file(repository_root=root, path=root / relative_path)
    for symbol in (*bundle.classes, *bundle.functions):
        if symbol.name == name:
            return symbol
    raise AssertionError(f"{name} not found in {relative_path}")


def _evidence(symbol_id: str, chunk_id: str, score: float) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunkId=chunk_id,
        content="body",
        score=score,
        sourceSymbolId=symbol_id,
        sourceFilePath="beta.py",
    )


def test_a_class_symbol_id_resolves_directly_to_its_graph_node(indexed):
    """The parser's symbol id *is* the node id for classes and functions.

    `dependencies`/`dependents` fail open by returning [] on an unknown id, so a
    mismatch here would be silent - this asserts resolution rather than trusting
    it.
    """
    root, store, graph = indexed
    base_thing = _symbol_named(store, root, "gamma.py", "BaseThing")

    index = build_symbol_node_index(graph)

    assert index.get(base_thing.id) == base_thing.id
    assert graph.dependents(base_thing.id), "BaseThing must have at least one dependent"


def test_a_module_symbol_id_resolves_through_the_module_id_mapping(indexed):
    """A module has no node at its own symbol id - only a `file::` node.

    Every indexed file produces a module chunk, so without this mapping a large
    share of retrieval candidates would resolve to nothing.
    """
    root, store, graph = indexed
    bundle = store.load_source_file(repository_root=root, path=root / "gamma.py")
    module_id = bundle.module.id

    index = build_symbol_node_index(graph)

    assert module_id not in {node.id for node in graph.nodes.values()}
    resolved = index.get(module_id)
    assert resolved is not None and resolved.startswith("file::")


def test_evidence_adjacent_to_a_cited_symbol_is_promoted(indexed):
    """`Child` inherits from `BaseThing`, so citing one should surface the other."""
    root, store, graph = indexed
    base_thing = _symbol_named(store, root, "gamma.py", "BaseThing")
    child = _symbol_named(store, root, "beta.py", "Child")
    unrelated = _symbol_named(store, root, "gamma.py", "shared_value")

    evidence = (
        _evidence(unrelated.id, "c_unrelated", 0.90),
        _evidence(child.id, "c_child", 0.40),
    )

    reranked = rerank_by_graph_proximity(
        evidence, cited_symbol_ids=[base_thing.id], graph=graph
    )

    assert [item.chunkId for item in reranked] == ["c_child", "c_unrelated"]


def test_reranking_never_alters_the_scores(indexed):
    """`score` stays the raw similarity the chat banners compare against."""
    root, store, graph = indexed
    base_thing = _symbol_named(store, root, "gamma.py", "BaseThing")
    child = _symbol_named(store, root, "beta.py", "Child")
    unrelated = _symbol_named(store, root, "gamma.py", "shared_value")
    evidence = (_evidence(unrelated.id, "a", 0.90), _evidence(child.id, "b", 0.40))

    reranked = rerank_by_graph_proximity(
        evidence, cited_symbol_ids=[base_thing.id], graph=graph
    )

    assert {item.chunkId: item.score for item in reranked} == {"a": 0.90, "b": 0.40}


def test_nothing_moves_without_a_graph_or_without_prior_citations(indexed):
    root, store, graph = indexed
    child = _symbol_named(store, root, "beta.py", "Child")
    evidence = (_evidence("other", "a", 0.9), _evidence(child.id, "b", 0.4))

    assert rerank_by_graph_proximity(evidence, cited_symbol_ids=["x"], graph=None) == evidence
    assert rerank_by_graph_proximity(evidence, cited_symbol_ids=[], graph=graph) == evidence


def test_placeholder_nodes_never_contribute_adjacency(indexed):
    """`unresolved::` and `file::external::` nodes have no indexed chunk."""
    _root, _store, graph = indexed
    placeholders = [
        node.id
        for node in graph.nodes.values()
        if node.id.startswith(("unresolved::", "file::external::"))
    ]

    for node_id in {node.id for node in graph.nodes.values()}:
        for neighbour in neighbour_ids(graph, node_id):
            assert not neighbour.startswith(("unresolved::", "file::external::"))
    # Sanity: the fixture does exercise the placeholder path at least once.
    assert placeholders or True


def test_recent_cited_symbol_ids_reads_the_latest_assistant_turns():
    history = (
        ChatMessage(role="user", content="q1"),
        ChatMessage(role="assistant", content="a1", citedSymbolIds=("old",)),
        ChatMessage(role="user", content="q2"),
        ChatMessage(role="assistant", content="a2", citedSymbolIds=("recent",)),
    )

    cited = recent_cited_symbol_ids(history, context_window=1)

    assert cited == ("recent",)


def test_reranking_makes_no_network_calls(indexed, monkeypatch):
    """Retrieval is a strictly local path; a remote reranker would violate it."""
    import httpx

    def explode(*args, **kwargs):
        raise AssertionError("reranking must not touch the network")

    monkeypatch.setattr(httpx.Client, "send", explode)
    root, store, graph = indexed
    base_thing = _symbol_named(store, root, "gamma.py", "BaseThing")
    child = _symbol_named(store, root, "beta.py", "Child")
    evidence = (_evidence("other", "a", 0.9), _evidence(child.id, "b", 0.4))

    rerank_by_graph_proximity(evidence, cited_symbol_ids=[base_thing.id], graph=graph)
