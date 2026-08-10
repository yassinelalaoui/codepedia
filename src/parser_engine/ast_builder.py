from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import ParseError
from .models import AST, ASTNode, Point


@dataclass(slots=True)
class ASTBuilder:
    def from_tree(
        self,
        *,
        language: str,
        parser_name: str,
        source_path: Path | str,
        tree: Any,
        has_errors: bool = False,
    ) -> AST:
        root = self._build_node(tree.root_node)
        return AST(
            language=language,
            root=root,
            source_path=str(source_path),
            has_errors=has_errors or bool(getattr(tree.root_node, "has_error", False)),
            parser_name=parser_name,
        )

    def from_outline(
        self,
        *,
        language: str,
        parser_name: str,
        source_path: Path | str,
        root_type: str,
        nodes: Iterable[ASTNode],
        has_errors: bool = False,
    ) -> AST:
        root = ASTNode(
            type=root_type,
            start_byte=0,
            end_byte=0,
            start_point=Point(0, 0),
            end_point=Point(0, 0),
            children=tuple(nodes),
        )
        return AST(
            language=language,
            root=root,
            source_path=str(source_path),
            has_errors=has_errors,
            parser_name=parser_name,
        )

    def leaf_node(
        self,
        *,
        node_type: str,
        start_byte: int,
        end_byte: int,
        start_point: tuple[int, int] | Point,
        end_point: tuple[int, int] | Point,
        named: bool = True,
        extra: bool = False,
        missing: bool = False,
    ) -> ASTNode:
        return ASTNode(
            type=node_type,
            start_byte=start_byte,
            end_byte=end_byte,
            start_point=start_point if isinstance(start_point, Point) else Point(*start_point),
            end_point=end_point if isinstance(end_point, Point) else Point(*end_point),
            named=named,
            extra=extra,
            missing=missing,
        )

    def _build_node(self, node: Any) -> ASTNode:
        children: list[ASTNode] = []
        fields: dict[str, ASTNode] = {}
        raw_children = list(getattr(node, "children", []) or [])
        for index, child in enumerate(raw_children):
            built_child = self._build_node(child)
            children.append(built_child)
            field_name = self._field_name_for_child(node, index, child)
            if field_name and field_name not in fields:
                fields[field_name] = built_child
        return ASTNode(
            type=str(getattr(node, "type", "unknown")),
            start_byte=int(getattr(node, "start_byte", 0)),
            end_byte=int(getattr(node, "end_byte", 0)),
            start_point=Point.from_value(getattr(node, "start_point", (0, 0))),
            end_point=Point.from_value(getattr(node, "end_point", (0, 0))),
            children=tuple(children),
            fields=fields,
            named=bool(getattr(node, "is_named", getattr(node, "named", True))),
            extra=bool(getattr(node, "is_extra", getattr(node, "extra", False))),
            missing=bool(getattr(node, "is_missing", getattr(node, "missing", False))),
        )

    def _field_name_for_child(self, node: Any, index: int, child: Any) -> str | None:
        field_for_index = getattr(node, "field_name_for_child", None)
        if callable(field_for_index):
            try:
                value = field_for_index(index)
                if value:
                    return str(value)
            except Exception:
                pass
        value = getattr(child, "field_name", None)
        if value:
            return str(value)
        return None


def build_line_ast(
    *,
    builder: ASTBuilder,
    language: str,
    parser_name: str,
    source_path: Path | str,
    root_type: str,
    source_text: str,
    items: list[tuple[str, str, int, int, int, int]],
    has_errors: bool = False,
) -> AST:
    nodes = [
        builder.leaf_node(
            node_type=node_type,
            start_byte=start_byte,
            end_byte=end_byte,
            start_point=(start_row, start_col),
            end_point=(end_row, end_col),
        )
        for node_type, _name, start_byte, end_byte, start_row, start_col, end_row, end_col in items
    ]
    return builder.from_outline(
        language=language,
        parser_name=parser_name,
        source_path=source_path,
        root_type=root_type,
        nodes=nodes,
        has_errors=has_errors,
    )


def validate_delimiters(text: str) -> None:
    pairs = {
        "(": ")",
        "{": "}",
        "[": "]",
    }
    closing = {
        ")": "(",
        "}": "{",
        "]": "[",
    }
    stack: list[str] = []
    for char in text:
        if char in pairs:
            stack.append(char)
        elif char in closing:
            if not stack or stack[-1] != closing[char]:
                raise ParseError(
                    source_path="<unknown>",
                    language="<unknown>",
                    parser_name="Parser",
                    message="unbalanced delimiters",
                    recoverable=True,
                )
            stack.pop()
    if stack:
        raise ParseError(
            source_path="<unknown>",
            language="<unknown>",
            parser_name="Parser",
            message="unbalanced delimiters",
            recoverable=True,
        )
