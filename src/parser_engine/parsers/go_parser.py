from __future__ import annotations

from ..models import SourceFile
from .common import TreeSitterOrFallbackParser, build_outline_fallback


class GoParser(TreeSitterOrFallbackParser):
    language_key = "go"
    parser_name = "GoParser"
    root_type = "source_file"

    def _parse_fallback(self, source_file: SourceFile, text: str):
        return build_outline_fallback(
            builder=self._builder,
            language=self.language_key,
            parser_name=self.parser_name,
            source_file=source_file,
            text=text,
            root_type=self.root_type,
        )

