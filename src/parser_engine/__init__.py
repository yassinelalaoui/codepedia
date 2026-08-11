from __future__ import annotations

from .errors import ParseError, ParserUnavailableError, UnsupportedLanguageError
from .extractor import SymbolExtractor, extract_symbols
from .inventory import CallRelation, FileSymbolInventory, ImportRecord, InheritanceRelation
from .models import AST, ASTNode, ParseFailure, ParseResult, Point, SourceFile
from .parser_base import Parser
from .parser_registry import (
    SUPPORTED_LANGUAGES,
    get_parser,
    parse_batch,
    parse_source_file,
    register_parser,
)
from .parsers import (
    GoParser,
    JavaParser,
    JavaScriptParser,
    PythonParser,
    RustParser,
    TypeScriptParser,
)
from .symbols import ClassSymbol, FunctionSymbol, ModuleSymbol, Parameter, Symbol

__all__ = [
    "AST",
    "ASTNode",
    "CallRelation",
    "ClassSymbol",
    "FileSymbolInventory",
    "FunctionSymbol",
    "GoParser",
    "ImportRecord",
    "InheritanceRelation",
    "JavaParser",
    "JavaScriptParser",
    "ModuleSymbol",
    "ParseError",
    "ParseFailure",
    "ParseResult",
    "Parser",
    "ParserUnavailableError",
    "Point",
    "Parameter",
    "PythonParser",
    "RustParser",
    "SourceFile",
    "Symbol",
    "SymbolExtractor",
    "SUPPORTED_LANGUAGES",
    "TypeScriptParser",
    "UnsupportedLanguageError",
    "extract_symbols",
    "get_parser",
    "parse_batch",
    "parse_source_file",
    "register_parser",
]
