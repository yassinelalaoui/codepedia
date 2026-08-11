from pathlib import Path

from parser_engine import SourceFile, extract_symbols


def test_inventory_serializes_with_shared_symbol_shape():
    source = SourceFile(
        path=Path("sample.py"),
        language="python",
        content='class A:\n    def run(self):\n        return helper()\n\ndef helper():\n    return 1\n',
    )
    inventory = extract_symbols(source)
    data = inventory.to_dict()

    assert data["module"]["generatedSummary"] == ""
    assert data["classes"]
    assert data["functions"]
    assert data["imports"] == []
    assert data["callRelations"]
    assert data["inheritanceRelations"] == []

