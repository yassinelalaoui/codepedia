from pathlib import Path

from parser_engine import SourceFile, TypeScriptParser


def test_typescript_parser_parses_interface():
    parser = TypeScriptParser()
    source = SourceFile(path=Path("sample.ts"), language="typescript", content="interface Foo { x: number }\n")
    ast = parser.parse(source)
    assert ast.language == "typescript"

