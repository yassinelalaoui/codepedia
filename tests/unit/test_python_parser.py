from pathlib import Path

from parser_engine import PythonParser, SourceFile


def test_python_parser_parses_module():
    parser = PythonParser()
    source = SourceFile(path=Path("sample.py"), language="python", content="class A:\n    def run(self):\n        return 1\n")
    ast = parser.parse(source)
    assert ast.language == "python"
    assert ast.root.children

