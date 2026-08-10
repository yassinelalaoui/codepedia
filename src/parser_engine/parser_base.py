from __future__ import annotations

from abc import ABC, abstractmethod

from .errors import ParseError
from .models import AST, ParseResult, SourceFile


class Parser(ABC):
    language: str = ""
    parser_name: str = "Parser"

    @abstractmethod
    def parse(self, source_file: SourceFile) -> AST:
        raise NotImplementedError

    def parse_result(self, source_file: SourceFile) -> ParseResult:
        try:
            ast = self.parse(source_file)
        except ParseError as exc:
            return ParseResult.from_failure(exc.to_failure())
        except Exception as exc:  # pragma: no cover - defensive
            error = ParseError.from_source_file(
                source_file,
                language=source_file.language,
                parser_name=self.parser_name,
                message=str(exc),
                recoverable=True,
            )
            return ParseResult.from_failure(error.to_failure())
        return ParseResult.from_ast(ast)

