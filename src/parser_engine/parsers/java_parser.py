from __future__ import annotations

from ..models import SourceFile
from .common import TreeSitterOrFallbackParser, build_outline_fallback


class JavaParser(TreeSitterOrFallbackParser):
    language_key = "java"
    parser_name = "JavaParser"
    root_type = "program"

    def _parse_fallback(self, source_file: SourceFile, text: str):
        return build_outline_fallback(
            builder=self._builder,
            language=self.language_key,
            parser_name=self.parser_name,
            source_file=source_file,
            text=text,
            root_type=self.root_type,
        )

