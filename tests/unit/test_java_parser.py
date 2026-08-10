from pathlib import Path

from parser_engine import JavaParser, SourceFile


def test_java_parser_parses_class():
    parser = JavaParser()
    source = SourceFile(path=Path("Sample.java"), language="java", content="class Sample { }\n")
    ast = parser.parse(source)
    assert ast.language == "java"

