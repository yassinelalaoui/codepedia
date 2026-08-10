from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import ParseFailure, SourceFile


@dataclass(slots=True)
class ParseError(Exception):
    source_path: str
    language: str
    parser_name: str
    message: str
    recoverable: bool = True

    def __str__(self) -> str:
        return f"{self.parser_name} failed for {self.source_path}: {self.message}"

    @classmethod
    def from_source_file(
        cls,
        source_file: SourceFile | Path | str,
        *,
        language: str,
        parser_name: str,
        message: str,
        recoverable: bool = True,
    ) -> "ParseError":
        if isinstance(source_file, SourceFile):
            path = source_file.path
        else:
            path = Path(source_file)
        return cls(
            source_path=str(path),
            language=language,
            parser_name=parser_name,
            message=message,
            recoverable=recoverable,
        )

    def to_failure(self) -> ParseFailure:
        return ParseFailure(
            source_path=self.source_path,
            language=self.language,
            parser_name=self.parser_name,
            message=self.message,
            recoverable=self.recoverable,
        )


class ParserUnavailableError(ParseError):
    pass


class UnsupportedLanguageError(ParseError):
    pass

