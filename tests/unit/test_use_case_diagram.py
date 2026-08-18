from __future__ import annotations

from dependency_graph import DependencyEdge, DependencyGraph, DependencyNode
from repository_metadata.models import FunctionSymbol
from repository_metadata.models import DependencyGraph as MetadataDependencyGraph
from repository_metadata.models import (
    Repository,
    RepositoryBundle,
    SourceFile,
    SourceFileBundle,
)
from repository_metadata import ModuleSymbol

from doc_generator.use_case_diagram import select_use_cases


def _module_symbol(source_file_id: str = "file1", name: str = "mod") -> ModuleSymbol:
    return ModuleSymbol(
        id=f"module-{source_file_id}",
        sourceFileId=source_file_id,
        kind="module",
        name=name,
        lineStart=1,
        lineEnd=100,
        filePath=f"{name}.py",
    )


def _source_file(source_file_id: str = "file1", path: str = "mod.py") -> SourceFile:
    return SourceFile(
        id=source_file_id,
        repositoryId="repo1",
        path=path,
        language="python",
        contentHash="hash",
        lastModified="2026-08-17T00:00:00Z",
    )


def _function_symbol(function_id: str, name: str, *, decorators: tuple[str, ...] = ()) -> FunctionSymbol:
    return FunctionSymbol(
        id=function_id,
        sourceFileId="file1",
        kind="function",
        name=name,
        lineStart=1,
        lineEnd=2,
        owner="module",
        metadata={"owner": "module", "returnType": None, "decorators": list(decorators)},
    )


def _bundle(functions: tuple[FunctionSymbol, ...]) -> RepositoryBundle:
    file_bundle = SourceFileBundle(file=_source_file(), module=_module_symbol(), classes=(), functions=functions)
    return RepositoryBundle(
        repository=Repository(id="repo1", rootPath="/repo"),
        files=(file_bundle,),
        graph=MetadataDependencyGraph(id="g1", repositoryId="repo1"),
    )


def _add_function_node(graph: DependencyGraph, function_id: str, name: str) -> DependencyNode:
    return graph.add_node(DependencyNode(id=function_id, kind="symbol", name=name, sourceFile="mod.py", symbolType="function"))


def test_select_use_cases_distinct_actors_for_cli_and_api():
    cli_function = _function_symbol("f1", "run_index", decorators=("app.command('index')",))
    api_function = _function_symbol("f2", "get_sessions", decorators=("app.get('/sessions')",))
    bundle = _bundle((cli_function, api_function))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "run_index")
    _add_function_node(graph, "f2", "get_sessions")

    result = select_use_cases(bundle, graph)

    assert [actor.kind for actor in result.actors] == ["cli-command", "api-route"]
    assert [actor.label for actor in result.actors] == ["CLI", "API"]
    assert len(result.useCases) == 2
    cli_use_case = next(uc for uc in result.useCases if uc.actorKind == "cli-command")
    api_use_case = next(uc for uc in result.useCases if uc.actorKind == "api-route")
    assert cli_use_case.label == "mod.run_index"
    assert api_use_case.label == "mod.get_sessions"


def test_select_use_cases_plain_function_connects_to_generic_actor():
    function = _function_symbol("f1", "standalone")
    bundle = _bundle((function,))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "standalone")

    result = select_use_cases(bundle, graph)

    assert [actor.kind for actor in result.actors] == ["function"]
    assert [actor.label for actor in result.actors] == ["External Caller"]
    assert len(result.useCases) == 1
    assert result.useCases[0].actorKind == "function"


def test_select_use_cases_shares_one_actor_across_same_kind_entry_points():
    first = _function_symbol("f1", "run_a", decorators=("app.command('a')",))
    second = _function_symbol("f2", "run_b", decorators=("app.command('b')",))
    bundle = _bundle((first, second))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "run_a")
    _add_function_node(graph, "f2", "run_b")

    result = select_use_cases(bundle, graph)

    assert len(result.actors) == 1
    assert result.actors[0].kind == "cli-command"
    assert len(result.useCases) == 2
    assert all(use_case.actorKind == "cli-command" for use_case in result.useCases)


def test_select_use_cases_returns_empty_selection_for_zero_entry_points():
    """a() and b() call each other, so both always have a caller - neither
    qualifies as an entry point (mirrors 022's own zero-entry-point case)."""
    function_a = _function_symbol("f1", "a")
    function_b = _function_symbol("f2", "b")
    bundle = _bundle((function_a, function_b))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "a")
    _add_function_node(graph, "f2", "b")
    graph._add_edge_object(
        DependencyEdge(sourceId="f1", targetId="f2", type="call", sourceFile="mod.py", metadata={})
    )
    graph._add_edge_object(
        DependencyEdge(sourceId="f2", targetId="f1", type="call", sourceFile="mod.py", metadata={})
    )

    result = select_use_cases(bundle, graph)

    assert result.actors == ()
    assert result.useCases == ()


def test_select_use_cases_actor_order_is_always_cli_api_generic_regardless_of_encounter_order():
    plain_function = _function_symbol("f1", "aaa_plain")
    api_function = _function_symbol("f2", "bbb_api", decorators=("app.get('/x')",))
    cli_function = _function_symbol("f3", "ccc_cli", decorators=("app.command('x')",))
    bundle = _bundle((plain_function, api_function, cli_function))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "aaa_plain")
    _add_function_node(graph, "f2", "bbb_api")
    _add_function_node(graph, "f3", "ccc_cli")

    result = select_use_cases(bundle, graph)

    assert [actor.kind for actor in result.actors] == ["cli-command", "api-route", "function"]
