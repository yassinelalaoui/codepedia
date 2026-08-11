from pathlib import Path

from parser_engine import SourceFile, extract_symbols


def test_python_fixture_produces_full_inventory():
    source_path = Path("tests/integration/fixtures/symbol-extractor/python/sample.py")
    inventory = extract_symbols(SourceFile(path=source_path, language="python"))

    assert inventory.module.name == "sample"
    assert [item.name for item in inventory.classes] == ["Base", "Child"]
    assert [item.name for item in inventory.functions] == ["method", "inner", "helper"]
    assert any(item.text.startswith("import os") for item in inventory.imports)
    assert any(rel.parentClassName == "Base" for rel in inventory.inheritanceRelations)
    assert any(rel.callerSymbolId == inventory.functions[0].id for rel in inventory.callRelations)


def test_javascript_fixture_produces_full_inventory():
    source_path = Path("tests/integration/fixtures/symbol-extractor/javascript/sample.js")
    inventory = extract_symbols(SourceFile(path=source_path, language="javascript"))

    assert inventory.module.name == "sample"
    assert [item.name for item in inventory.classes] == ["Child"]
    assert [item.name for item in inventory.functions] == ["method", "inner", "helper"]
    assert any(item.text.startswith('import { a } from "x"') for item in inventory.imports)
    assert inventory.classes[0].parentClass == "Base"
    assert any(rel.callerSymbolId == inventory.functions[0].id for rel in inventory.callRelations)

