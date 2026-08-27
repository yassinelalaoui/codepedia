from pathlib import Path

from parser_engine import JavaScriptParser, PythonParser, SourceFile


def test_parser_interface_returns_ast():
    parser = PythonParser()
    source = SourceFile(path=Path("sample.py"), language="python", content="def foo():\n    return 1\n")
    ast = parser.parse(source)
    assert ast.language == "python"
    assert ast.parser_name == "PythonParser"
    # tree-sitter names the root "module", the `ast`-module fallback "Module".
    assert ast.root.type.lower() == "module"


def test_parser_interface_works_for_js():
    parser = JavaScriptParser()
    source = SourceFile(path=Path("sample.js"), language="javascript", content="function foo() { return 1; }\n")
    ast = parser.parse(source)
    assert ast.language == "javascript"
    assert ast.root.type == "program"

