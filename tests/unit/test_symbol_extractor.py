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

