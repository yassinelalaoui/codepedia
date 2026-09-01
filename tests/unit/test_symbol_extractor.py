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



def _python_ids(content: str) -> dict[str, str]:
    inventory = extract_symbols(SourceFile(path=Path("sample.py"), language="python", content=content))
    symbols = [inventory.module, *inventory.classes, *inventory.functions]
    return {f"{type(symbol).__name__}:{symbol.name}": symbol.id for symbol in symbols}


def test_symbol_ids_survive_a_line_inserted_above_them():
    """The property the whole id scheme exists for.

    The mirror of `test_heading_ids_survive_a_paragraph_inserted_above_them`
    for code. Ids used to seed on `lineStart`/`lineEnd`, so one added import
    rewrote the id of every symbol below it - and with it every anchor, every
    `search-index.json` entry, every vector chunk key and every stored chat
    citation, none of whose subjects had changed.
    """
    before = "import os\n\n\nclass Widget:\n    def render(self):\n        return 1\n\n\ndef helper():\n    return 2\n"
    after = "import os\nimport sys\n\n\nclass Widget:\n    def render(self):\n        return 1\n\n\ndef helper():\n    return 2\n"

    assert _python_ids(before) == _python_ids(after)

    # The spans really did move; it is only the identity that held still.
    moved = extract_symbols(SourceFile(path=Path("sample.py"), language="python", content=after))
    original = extract_symbols(SourceFile(path=Path("sample.py"), language="python", content=before))
    assert moved.classes[0].lineStart != original.classes[0].lineStart


def test_same_method_name_under_two_classes_gets_distinct_ids():
    inventory = extract_symbols(
        SourceFile(
            path=Path("sample.py"),
            language="python",
            content="class A:\n    def run(self):\n        pass\n\n\nclass B:\n    def run(self):\n        pass\n",
        )
    )
    identifiers = [item.id for item in inventory.functions]
    assert len(identifiers) == 2
    assert len(set(identifiers)) == 2


def test_homonyms_in_one_file_get_distinct_ids():
    """Two definitions of the same qualified name, told apart by ordinal alone.

    A redefinition is the ordinary way this happens; without the ordinal both
    would hash to one id, and `symbols.id`'s UNIQUE constraint would reject the
    whole file on insert.
    """
    inventory = extract_symbols(
        SourceFile(
            path=Path("sample.py"),
            language="python",
            content="def parse():\n    return 1\n\n\ndef parse():\n    return 2\n",
        )
    )
    identifiers = [item.id for item in inventory.functions if item.name == "parse"]
    assert len(identifiers) == 2
    assert len(set(identifiers)) == 2


def test_adding_a_symbol_above_does_not_shift_an_unrelated_homonym_ordinal():
    """The ordinal counts per (kind, qualified name), not per file.

    Keyed on the name alone, declaring a *differently* named function above
    `parse` would renumber it and change its id - reintroducing positional
    identity through the back door.
    """
    before = _python_ids("def parse():\n    return 1\n")
    after = _python_ids("def scan():\n    return 0\n\n\ndef parse():\n    return 1\n")
    assert before["FunctionSymbol:parse"] == after["FunctionSymbol:parse"]


def test_symbol_ids_do_not_depend_on_the_path_separator():
    content = "def helper():\n    return 1\n"
    windows = extract_symbols(SourceFile(path=Path(r"pkg\mod.py"), language="python", content=content))
    posix = extract_symbols(SourceFile(path=Path("pkg/mod.py"), language="python", content=content))
    assert windows.module.id == posix.module.id
    assert windows.functions[0].id == posix.functions[0].id
