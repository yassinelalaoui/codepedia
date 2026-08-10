from pathlib import Path

from parser_engine import GoParser, SourceFile


def test_go_parser_parses_function():
    parser = GoParser()
    source = SourceFile(path=Path("sample.go"), language="go", content="package main\nfunc main() {}\n")
    ast = parser.parse(source)
    assert ast.language == "go"

