from pathlib import Path

from parser_engine import RustParser, SourceFile


def test_rust_parser_parses_function():
    parser = RustParser()
    source = SourceFile(path=Path("sample.rs"), language="rust", content="fn main() {}\n")
    ast = parser.parse(source)
    assert ast.language == "rust"

