from __future__ import annotations

from dependency_graph import DependencyEdge, DependencyGraph, DependencyNode
from repository_metadata.models import (
    ClassSymbol,
    FunctionSymbol,
)
from repository_metadata.models import DependencyGraph as MetadataDependencyGraph
from repository_metadata.models import (
    Repository,
    RepositoryBundle,
    SourceFile,
    SourceFileBundle,
)
from repository_metadata import ModuleSymbol

from doc_generator.entry_point_diagram import (
    EntryPoint,
    build_entry_point_call_sequence,
    identify_entry_points,
)


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


def _function_symbol(
    function_id: str,
    name: str,
    *,
    owner: str = "module",
    decorators: tuple[str, ...] = (),
    nested_symbols: tuple[str, ...] = (),
) -> FunctionSymbol:
    return FunctionSymbol(
        id=function_id,
        sourceFileId="file1",
        kind="function",
        name=name,
        lineStart=1,
        lineEnd=2,
        owner=owner,
        nestedSymbols=nested_symbols,
        metadata={"owner": owner, "returnType": None, "decorators": list(decorators)},
    )


def _bundle(
    functions: tuple[FunctionSymbol, ...],
    *,
    classes: tuple[ClassSymbol, ...] = (),
    source_file_id: str = "file1",
    module_name: str = "mod",
) -> RepositoryBundle:
    file_bundle = SourceFileBundle(
        file=_source_file(source_file_id, path=f"{module_name}.py"),
        module=_module_symbol(source_file_id, module_name),
        classes=classes,
        functions=functions,
    )
    return RepositoryBundle(
        repository=Repository(id="repo1", rootPath="/repo"),
        files=(file_bundle,),
        graph=MetadataDependencyGraph(id="g1", repositoryId="repo1"),
    )


def _add_function_node(graph: DependencyGraph, function_id: str, name: str, *, source_file: str = "mod.py") -> DependencyNode:
    return graph.add_node(
        DependencyNode(id=function_id, kind="symbol", name=name, sourceFile=source_file, symbolType="function")
    )


def _add_call_edge(graph: DependencyGraph, source_id: str, target_id: str, *, line_start: int) -> None:
    graph._add_edge_object(
        DependencyEdge(sourceId=source_id, targetId=target_id, type="call", sourceFile="mod.py", metadata={"lineStart": line_start})
    )


# --- identify_entry_points ---------------------------------------------------


def test_identify_entry_points_includes_a_function_nothing_calls():
    bundle = _bundle((_function_symbol("f1", "standalone"),))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "standalone")

    result = identify_entry_points(bundle, graph)

    assert len(result) == 1
    assert result[0].symbolId == "f1"
    assert result[0].kind == "function"


def test_identify_entry_points_excludes_a_function_called_by_another_function():
    bundle = _bundle((_function_symbol("f1", "caller"), _function_symbol("f2", "callee")))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "caller")
    _add_function_node(graph, "f2", "callee")
    _add_call_edge(graph, "f1", "f2", line_start=5)

    result = identify_entry_points(bundle, graph)

    names = {entry_point.name for entry_point in result}
    assert "caller" in names
    assert "callee" not in names


def test_identify_entry_points_includes_cli_decorated_method_even_when_called():
    method = _function_symbol("m1", "run", owner="class", decorators=("app.command('run')",))
    caller = _function_symbol("f1", "caller")
    class_symbol = ClassSymbol(id="c1", sourceFileId="file1", kind="class", name="Service", lineStart=1, lineEnd=10, methods=("m1",))
    bundle = _bundle((caller, method), classes=(class_symbol,))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "caller")
    _add_function_node(graph, "m1", "run")
    _add_call_edge(graph, "f1", "m1", line_start=3)

    result = identify_entry_points(bundle, graph)

    run_entry = next(entry_point for entry_point in result if entry_point.name == "run")
    assert run_entry.kind == "cli-command"
    assert run_entry.className == "Service"


def test_identify_entry_points_includes_api_route_decorated_function():
    function = _function_symbol("f1", "get_sessions", decorators=("app.get('/sessions')",))
    bundle = _bundle((function,))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "get_sessions")

    result = identify_entry_points(bundle, graph)

    assert result[0].kind == "api-route"


def test_identify_entry_points_includes_function_called_only_from_module_level_code():
    """A function invoked only via an `if __name__ == "__main__":` guard is
    called by the module (a file-kind node), not by another function - so it
    still qualifies (Research Decision 2)."""
    function = _function_symbol("f1", "main")
    bundle = _bundle((function,))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "main")
    module_node = graph.add_node(
        DependencyNode(id="file::mod.py", kind="file", name="mod", sourceFile="mod.py", symbolType="module")
    )
    _add_call_edge(graph, module_node.id, "f1", line_start=10)

    result = identify_entry_points(bundle, graph)

    assert len(result) == 1
    assert result[0].name == "main"


def test_identify_entry_points_excludes_private_and_nested_functions():
    outer = _function_symbol("f1", "outer", nested_symbols=("f2",))
    nested = _function_symbol("f2", "inner")
    private = _function_symbol("f3", "_hidden")
    bundle = _bundle((outer, nested, private))
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "outer")
    _add_function_node(graph, "f2", "inner")
    _add_function_node(graph, "f3", "_hidden")

    result = identify_entry_points(bundle, graph)

    names = {entry_point.name for entry_point in result}
    assert names == {"outer"}


def test_identify_entry_points_returns_empty_tuple_for_zero_candidates():
    bundle = _bundle(())
    graph = DependencyGraph(id="g1", sourceFile="repo")

    result = identify_entry_points(bundle, graph)

    assert result == ()


# --- build_entry_point_call_sequence -----------------------------------------


def _entry_point(symbol_id: str = "f1", name: str = "entry") -> EntryPoint:
    return EntryPoint(
        symbolId=symbol_id,
        stableKey=f"file1::module::{name}",
        name=name,
        moduleKey="file1",
        moduleName="mod",
        className=None,
        kind="function",
    )


def test_build_entry_point_call_sequence_orders_steps_by_call_site_line_not_insertion():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "entry", source_file="a.py")
    _add_function_node(graph, "f2", "second", source_file="b.py")
    _add_function_node(graph, "f3", "first", source_file="c.py")
    # Insert the later-in-source call first, to prove ordering is by lineStart, not insertion.
    _add_call_edge(graph, "f1", "f2", line_start=20)
    _add_call_edge(graph, "f1", "f3", line_start=5)

    def resolve_module(source_file):
        return {"a.py": ("file1", "a"), "b.py": ("file2", "b"), "c.py": ("file3", "c")}.get(source_file)

    result = build_entry_point_call_sequence(graph, _entry_point(), resolve_module=resolve_module)

    assert [step.calleeName for step in result.steps] == ["first", "second"]
    assert result.steps[0].calleeModuleName == "c"
    assert result.steps[1].calleeModuleName == "b"
    assert result.truncatedAtMaxDepth is False


def test_build_entry_point_call_sequence_leaf_entry_point_has_no_steps():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "entry")

    result = build_entry_point_call_sequence(graph, _entry_point())

    assert result.steps == ()
    assert result.truncatedAtMaxDepth is False


def test_build_entry_point_call_sequence_self_recursive_function_stops_at_max_depth():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "recursive_fn")
    _add_call_edge(graph, "f1", "f1", line_start=1)

    result = build_entry_point_call_sequence(graph, _entry_point(), max_depth=6)

    assert len(result.steps) == 6
    assert all(step.calleeName == "recursive_fn" for step in result.steps)
    assert result.truncatedAtMaxDepth is True


def test_build_entry_point_call_sequence_two_function_cycle_terminates_at_max_depth():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "a", "a")
    _add_function_node(graph, "b", "b")
    _add_call_edge(graph, "a", "b", line_start=1)
    _add_call_edge(graph, "b", "a", line_start=1)

    result = build_entry_point_call_sequence(graph, _entry_point(symbol_id="a", name="a"), max_depth=6)

    assert len(result.steps) == 6
    assert [step.calleeName for step in result.steps] == ["b", "a", "b", "a", "b", "a"]
    assert result.truncatedAtMaxDepth is True


def test_build_entry_point_call_sequence_unresolved_target_still_produces_a_step():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "entry")
    _add_function_node(graph, "f2", "external_thing", source_file="<unknown>")
    _add_call_edge(graph, "f1", "f2", line_start=1)

    result = build_entry_point_call_sequence(graph, _entry_point(), resolve_module=lambda _sourceFile: None)

    assert len(result.steps) == 1
    assert result.steps[0].calleeModuleKey is None
    assert result.steps[0].calleeModuleName is None
    assert result.steps[0].calleeName == "external_thing"


def test_build_entry_point_call_sequence_two_call_sites_to_same_target_collapse_to_one_step():
    graph = DependencyGraph(id="g1", sourceFile="repo")
    _add_function_node(graph, "f1", "entry")
    _add_function_node(graph, "f2", "callee")
    _add_call_edge(graph, "f1", "f2", line_start=5)

    result = build_entry_point_call_sequence(graph, _entry_point())

    assert len(result.steps) == 1
