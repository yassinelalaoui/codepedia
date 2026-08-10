from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

from .errors import ParseError, UnsupportedLanguageError
from .models import ParseResult, SourceFile
from .parser_base import Parser
from .parsers import (
    GoParser,
    JavaParser,
    JavaScriptParser,
    PythonParser,
    RustParser,
    TypeScriptParser,
)

LOGGER = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("go", "java", "javascript", "python", "rust", "typescript")

_REGISTRY: dict[str, type[Parser]] = {}


def normalize_language(language: str) -> str:
    value = language.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if value in {"py", "python"}:
        return "python"
    if value in {"js", "javascript", "ecmascript"}:
        return "javascript"
    if value in {"ts", "typescript"}:
        return "typescript"
    if value in {"java"}:
        return "java"
    if value in {"go", "golang"}:
        return "go"
    if value in {"rust", "rs"}:
        return "rust"
    return value


def register_parser(language: str, parser_cls: type[Parser]) -> None:
    _REGISTRY[normalize_language(language)] = parser_cls


def get_parser(language: str) -> Parser:
    key = normalize_language(language)
    parser_cls = _REGISTRY.get(key)
    if parser_cls is None:
        raise UnsupportedLanguageError(
            source_path="<unknown>",
            language=language,
            parser_name="ParserRegistry",
            message=f"unsupported language: {language}",
            recoverable=False,
        )
    return parser_cls()


def parse_source_file(source_file: SourceFile, parser: Parser | None = None) -> ParseResult:
    parser = parser or get_parser(source_file.language)
    try:
        return parser.parse_result(source_file)
    except ParseError as exc:
        LOGGER.warning("parse failure for %s: %s", source_file.path, exc.message)
        return ParseResult.from_failure(exc.to_failure())


def parse_batch(source_files: Iterable[SourceFile]) -> list[ParseResult]:
    results: list[ParseResult] = []
    for source_file in source_files:
        try:
            results.append(parse_source_file(source_file))
        except ParseError as exc:
            LOGGER.warning("parse failure for %s: %s", source_file.path, exc.message)
            results.append(ParseResult.from_failure(exc.to_failure()))
        except Exception as exc:  # pragma: no cover - defensive
            failure = ParseError.from_source_file(
                source_file,
                language=source_file.language,
                parser_name="ParserRegistry",
                message=str(exc),
                recoverable=True,
            )
            LOGGER.warning("parse failure for %s: %s", source_file.path, failure.message)
            results.append(ParseResult.from_failure(failure.to_failure()))
    return results


def supported_parsers() -> dict[str, Parser]:
    return {language: get_parser(language) for language in SUPPORTED_LANGUAGES}


def _bootstrap_registry() -> None:
    register_parser("python", PythonParser)
    register_parser("javascript", JavaScriptParser)
    register_parser("typescript", TypeScriptParser)
    register_parser("java", JavaParser)
    register_parser("go", GoParser)
    register_parser("rust", RustParser)


_bootstrap_registry()

