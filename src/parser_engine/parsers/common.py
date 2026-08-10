from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..ast_builder import ASTBuilder, build_line_ast, validate_delimiters
from ..errors import ParseError, ParserUnavailableError
from ..models import AST, SourceFile
from ..parser_base import Parser
from ..treesitter_runtime import get_runtime, normalize_language_key


class TreeSitterOrFallbackParser(Parser):
    language_key: str = ""
    parser_name: str = "Parser"
    root_type: str = "module"

    def __init__(self) -> None:
        self._builder = ASTBuilder()

    def parse(self, source_file: SourceFile) -> AST:
        text = source_file.read_text()
        key = normalize_language_key(self.language_key or source_file.language)
        runtime = get_runtime()
        if runtime.is_available(key):
            try:
                tree = runtime.parse(key, text)
                return self._builder.from_tree(
                    language=self.display_language,
                    parser_name=self.parser_name,
                    source_path=source_file.path,
                    tree=tree,
                )
            except Exception as exc:
                raise ParseError.from_source_file(
                    source_file,
                    language=self.display_language,
                    parser_name=self.parser_name,
                    message=str(exc),
                    recoverable=True,
                )
        return self._parse_fallback(source_file, text)

    @property
    def display_language(self) -> str:
        return self.language_key or self.language or "unknown"

    def _parse_fallback(self, source_file: SourceFile, text: str) -> AST:
        raise ParserUnavailableError.from_source_file(
            source_file,
            language=self.display_language,
            parser_name=self.parser_name,
            message="tree-sitter runtime unavailable",
            recoverable=True,
        )


DECLARATION_PATTERNS = {
    "javascript": [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"), "function_declaration"),
        (re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"), "class_declaration"),
        (re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"), "interface_declaration"),
        (re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)"), "type_alias_declaration"),
    ],
    "typescript": [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"), "function_declaration"),
        (re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"), "class_declaration"),
        (re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"), "interface_declaration"),
        (re.compile(r"^\s*(?:export\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)"), "type_alias_declaration"),
    ],
    "java": [
        (re.compile(r"^\s*(?:public|protected|private|abstract|final|static|\s)*class\s+([A-Za-z_][A-Za-z0-9_]*)"), "class_declaration"),
        (re.compile(r"^\s*(?:public|protected|private|abstract|final|static|\s)*interface\s+([A-Za-z_][A-Za-z0-9_]*)"), "interface_declaration"),
        (re.compile(r"^\s*(?:public|protected|private|abstract|final|static|\s)*enum\s+([A-Za-z_][A-Za-z0-9_]*)"), "enum_declaration"),
    ],
    "go": [
        (re.compile(r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)"), "function_declaration"),
        (re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b"), "struct_declaration"),
        (re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+interface\b"), "interface_declaration"),
    ],
    "rust": [
        (re.compile(r"^\s*fn\s+([A-Za-z_][A-Za-z0-9_]*)"), "function_item"),
        (re.compile(r"^\s*struct\s+([A-Za-z_][A-Za-z0-9_]*)"), "struct_item"),
        (re.compile(r"^\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)"), "enum_item"),
        (re.compile(r"^\s*trait\s+([A-Za-z_][A-Za-z0-9_]*)"), "trait_item"),
        (re.compile(r"^\s*impl\b"), "impl_item"),
    ],
}


def build_outline_fallback(
    *,
    builder: ASTBuilder,
    language: str,
    parser_name: str,
    source_file: SourceFile,
    text: str,
    root_type: str = "module",
) -> AST:
    validate_delimiters(text)
    lines = text.splitlines(keepends=True)
    patterns = DECLARATION_PATTERNS.get(language, [])
    items: list[tuple[str, str, int, int, int, int, int, int]] = []
    byte_offset = 0
    for row, line in enumerate(lines):
        for regex, node_type in patterns:
            match = regex.match(line)
            if match:
                start_col = match.start(1) if match.groups() else match.start()
                end_col = match.end(1) if match.groups() else match.end()
                start_byte = byte_offset + start_col
                end_byte = byte_offset + end_col
                items.append(
                    (
                        node_type,
                        match.group(1) if match.groups() else "",
                        start_byte,
                        end_byte,
                        row,
                        start_col,
                        row,
                        end_col,
                    )
                )
                break
        byte_offset += len(line.encode("utf-8"))
    if not items and text.strip():
        total_bytes = len(text.encode("utf-8"))
        items.append(("source_file", "", 0, total_bytes, 0, 0, 0, len(text)))
    return build_line_ast(
        builder=builder,
        language=language,
        parser_name=parser_name,
        source_path=source_file.path,
        root_type=root_type,
        source_text=text,
        items=items,
    )
