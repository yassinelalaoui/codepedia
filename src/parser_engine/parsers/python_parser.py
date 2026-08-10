from __future__ import annotations

import ast as py_ast

from ..ast_builder import ASTBuilder
from ..errors import ParseError
from ..models import AST, ASTNode, Point, SourceFile
from .common import TreeSitterOrFallbackParser


class PythonParser(TreeSitterOrFallbackParser):
    language_key = "python"
    parser_name = "PythonParser"
    root_type = "module"

    def _parse_fallback(self, source_file: SourceFile, text: str) -> AST:
        try:
            tree = py_ast.parse(text)
        except SyntaxError as exc:
            raise ParseError.from_source_file(
                source_file,
                language=self.language_key,
                parser_name=self.parser_name,
                message=str(exc),
                recoverable=True,
            )
        root = self._convert_python_node(tree, text)
        return AST(
            language=self.language_key,
            root=root,
            source_path=str(source_file.path),
            has_errors=False,
            parser_name=self.parser_name,
        )

    def _convert_python_node(self, node: py_ast.AST, text: str) -> ASTNode:
        children: list[ASTNode] = []
        fields: dict[str, ASTNode] = {}
        for field_name, value in py_ast.iter_fields(node):
            if isinstance(value, py_ast.AST):
                built = self._convert_python_node(value, text)
                children.append(built)
                fields.setdefault(field_name, built)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, py_ast.AST):
                        built = self._convert_python_node(item, text)
                        children.append(built)
        start_line = getattr(node, "lineno", 1) - 1
        start_col = getattr(node, "col_offset", 0)
        end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1
        end_col = getattr(node, "end_col_offset", getattr(node, "col_offset", 0))
        start_byte = _linecol_to_byte_offset(text, start_line, start_col)
        end_byte = _linecol_to_byte_offset(text, end_line, end_col)
        return ASTNode(
            type=type(node).__name__,
            start_byte=start_byte,
            end_byte=end_byte,
            start_point=Point(start_line, start_col),
            end_point=Point(end_line, end_col),
            children=tuple(children),
            fields=fields,
            named=True,
            extra=False,
            missing=False,
        )


def _linecol_to_byte_offset(text: str, row: int, column: int) -> int:
    if row < 0:
        return 0
    lines = text.splitlines(keepends=True)
    prefix = "".join(lines[:row])
    if row < len(lines):
        prefix += lines[row][:column]
    return len(prefix.encode("utf-8"))

