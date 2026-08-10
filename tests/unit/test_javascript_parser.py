from pathlib import Path

from parser_engine import JavaScriptParser, SourceFile


def test_javascript_parser_parses_function():
    parser = JavaScriptParser()
    source = SourceFile(path=Path("sample.js"), language="javascript", content="function foo() { return 1; }\n")
    ast = parser.parse(source)
    assert ast.language == "javascript"

