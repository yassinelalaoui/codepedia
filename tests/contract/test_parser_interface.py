from pathlib import Path

from parser_engine import JavaScriptParser, PythonParser, SourceFile


def test_parser_interface_returns_ast():
    parser = PythonParser()
    source = SourceFile(path=Path("sample.py"), language="python", content="def foo():\n    return 1\n")
    ast = parser.parse(source)
    assert ast.language == "python"
    assert ast.parser_name == "PythonParser"
    assert ast.root.type == "Module"


def test_parser_interface_works_for_js():
    parser = JavaScriptParser()
    source = SourceFile(path=Path("sample.js"), language="javascript", content="function foo() { return 1; }\n")
    ast = parser.parse(source)
    assert ast.language == "javascript"
    assert ast.root.type == "program"

