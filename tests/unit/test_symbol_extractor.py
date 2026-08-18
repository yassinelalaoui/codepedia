from pathlib import Path

from parser_engine import SourceFile, extract_symbols


PYTHON_SAMPLE = '''"""Module doc."""

import os
from pkg import mod

class Base:
    pass

class Child(Base):
    """Child doc."""

    def method(self, x: int) -> str:
        """Method doc."""
        def inner(y: int) -> int:
            return helper(y)

        return helper(x) + inner(x)


def helper(value: int) -> int:
    return value
'''


def test_extract_python_symbols_and_relations():
    inventory = extract_symbols(SourceFile(path=Path("sample.py"), language="python", content=PYTHON_SAMPLE))

    assert inventory.module.docstring == "Module doc."
    assert [item.name for item in inventory.classes] == ["Base", "Child"]
    assert [item.name for item in inventory.functions] == ["method", "inner", "helper"]
    assert inventory.classes[1].parentClass == "Base"
    assert inventory.classes[1].methods[0].name == "method"
    assert inventory.functions[0].parameters[0].name == "self"
    assert inventory.functions[0].parameters[1].name == "x"
    assert inventory.functions[0].returnType == "str"
    assert inventory.functions[1].nestedSymbols == ()
    assert inventory.imports and any("import os" in item.text for item in inventory.imports)
    assert any(rel.parentClassName == "Base" for rel in inventory.inheritanceRelations)
    assert any(rel.callerSymbolId == inventory.functions[0].id for rel in inventory.callRelations)


NESTED_CLASS_SAMPLE = '''class Outer:
    class Inner:
        pass


def factory():
    class Local:
        pass

    return Local


class WithNestedFactory:
    def make(self):
        class DeeplyNested:
            pass

        return DeeplyNested
'''


DECORATED_SAMPLE = '''app = object()


@app.command("index")
def index_command():
    pass


@app.get("/sessions")
def get_sessions():
    pass


def plain():
    pass


class Service:
    @app.command("run")
    def run(self):
        pass
'''


def test_python_functions_capture_decorator_text():
    inventory = extract_symbols(SourceFile(path=Path("decorated.py"), language="python", content=DECORATED_SAMPLE))

    functions_by_name = {item.name: item for item in inventory.functions}
    assert any("app.command" in decorator for decorator in functions_by_name["index_command"].decorators)
    assert any("app.get" in decorator for decorator in functions_by_name["get_sessions"].decorators)
    assert functions_by_name["plain"].decorators == ()
    assert any("app.command" in decorator for decorator in functions_by_name["run"].decorators)


def test_nested_classes_are_not_duplicated_in_the_flattened_inventory():
    """Regression test: a class nested inside another class, inside a
    function, or inside a method used to be counted twice (once via a
    direct append to the shared `classes` list inside `build_class`/
    `build_function`, and again via the caller re-adding it from the
    returned result), producing two Symbol objects with the identical
    `id` - which crashed `repository_metadata`'s `symbols.id` UNIQUE
    constraint on insert. See specs/020-cli-packaging follow-up fix."""
    inventory = extract_symbols(SourceFile(path=Path("nested.py"), language="python", content=NESTED_CLASS_SAMPLE))

    names = [item.name for item in inventory.classes]
    assert names == ["Outer", "Inner", "Local", "WithNestedFactory", "DeeplyNested"]

    ids = [item.id for item in inventory.classes]
    assert len(ids) == len(set(ids)), f"duplicate class ids in flattened inventory: {ids}"

