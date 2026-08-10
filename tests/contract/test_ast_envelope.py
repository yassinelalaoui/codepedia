from pathlib import Path

from parser_engine import AST, ASTNode, Point, SourceFile
from parser_engine.ast_builder import ASTBuilder


def test_ast_envelope_is_uniform():
    builder = ASTBuilder()
    child = builder.leaf_node(
        node_type="function_declaration",
        start_byte=0,
        end_byte=10,
        start_point=(0, 0),
        end_point=(0, 10),
    )
    ast = builder.from_outline(
        language="python",
        parser_name="PythonParser",
        source_path=Path("sample.py"),
        root_type="module",
        nodes=[child],
    )
    assert isinstance(ast, AST)
    assert ast.language == "python"
    assert ast.root.children[0].type == "function_declaration"
    assert ast.root.start_point == Point(0, 0)

