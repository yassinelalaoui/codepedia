"""Reorder retrieved evidence using the repository's own call graph.

Vector and lexical similarity both judge a chunk on its text alone. The
dependency graph knows something neither does: that a chunk's symbol calls, is
called by, or inherits from a symbol the conversation is already discussing. On
a follow-up question ("and how does that get invoked?") that structural link is
usually a better relevance signal than any wording overlap.

The graph is built and persisted by `dependency_graph` at index time, and was
already consumed by documentation generation and by summarization prompts. This
is the retrieval path finally reading it too.

Everything here is local and in-memory: no model is called, no request is made.
`tests/unit/test_chat_retrieval.py` neutralizes `httpx` and fails if retrieval
touches the network, and reranking runs inside that same boundary.
"""

from __future__ import annotations

from typing import Any, Iterable

from .models import ChatMessage, RetrievedEvidence

# Nodes the graph synthesizes for a call or import it could not resolve to a
# real symbol. They never correspond to an indexed chunk, so they must never
# contribute adjacency.
PLACEHOLDER_NODE_PREFIXES = ("unresolved::", "file::external::")

DEFAULT_CONTEXT_WINDOW = 3


def recent_cited_symbol_ids(
    history: Iterable[ChatMessage], *, context_window: int = DEFAULT_CONTEXT_WINDOW
) -> tuple[str, ...]:
    """Symbols cited by the most recent assistant turns, newest first."""
    assistant_turns = [message for message in history if message.role == "assistant"]
    recent = assistant_turns[-context_window:] if context_window > 0 else []
    cited: list[str] = []
    for message in reversed(recent):
        cited.extend(message.citedSymbolIds)
    return tuple(dict.fromkeys(cited))


def build_symbol_node_index(graph: Any) -> dict[str, str]:
    """Map a chunk's `sourceSymbolId` onto the graph node that represents it.

    Classes and functions are direct: the parser's symbol id *is* the node id.
    Modules are not - the graph stores a module as a `file::<path>` node and
    keeps the module symbol id only in `metadata["moduleId"]`. Since every
    indexed file produces a module chunk, skipping that mapping would leave a
    large share of candidates unresolvable. Going through `moduleId` rather than
    the file path also sidesteps a path mismatch: chunks carry a repository-
    relative path while graph nodes are built from absolute ones.
    """
    index: dict[str, str] = {}
    for node in graph.nodes.values():
        index.setdefault(node.id, node.id)
        module_id = (node.metadata or {}).get("moduleId")
        if module_id:
            index.setdefault(str(module_id), node.id)
    return index


def neighbour_ids(graph: Any, node_id: str) -> set[str]:
    """Direct neighbours in both directions, placeholders excluded.

    `dependents` and `dependencies` are depth-1 only, and both fail open on an
    unknown id by returning an empty list.
    """
    neighbours: set[str] = set()
    for node in (*graph.dependents(node_id), *graph.dependencies(node_id)):
        if node.id.startswith(PLACEHOLDER_NODE_PREFIXES):
            continue
        neighbours.add(node.id)
        module_id = (node.metadata or {}).get("moduleId")
        if module_id:
            neighbours.add(str(module_id))
    return neighbours


def rerank_by_graph_proximity(
    evidence: tuple[RetrievedEvidence, ...],
    *,
    cited_symbol_ids: Iterable[str],
    graph: Any | None,
) -> tuple[RetrievedEvidence, ...]:
    """Move graph-adjacent evidence ahead, preserving relative order otherwise.

    A stable partition rather than a rescoring pass: `RetrievedEvidence.score`
    stays the raw similarity the chat layer compares against absolute thresholds,
    exactly as hybrid fusion leaves it alone.

    Returns `evidence` untouched whenever there is nothing to act on - no graph
    configured, no prior citations, or nothing adjacent among the candidates.
    """
    cited = tuple(dict.fromkeys(cited_symbol_ids))
    if graph is None or not cited or len(evidence) < 2:
        return evidence

    symbol_to_node = build_symbol_node_index(graph)
    adjacent: set[str] = set()
    for symbol_id in cited:
        node_id = symbol_to_node.get(symbol_id)
        if node_id is None:
            continue
        adjacent |= neighbour_ids(graph, node_id)
    if not adjacent:
        return evidence

    def is_adjacent(item: RetrievedEvidence) -> bool:
        if item.sourceSymbolId in adjacent:
            return True
        node_id = symbol_to_node.get(item.sourceSymbolId)
        return node_id is not None and node_id in adjacent

    boosted = [item for item in evidence if is_adjacent(item)]
    if not boosted or len(boosted) == len(evidence):
        return evidence
    remainder = [item for item in evidence if not is_adjacent(item)]
    return tuple([*boosted, *remainder])
