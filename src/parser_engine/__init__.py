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
# Exported under `Extracted*` names, and only under those. `repository_metadata
# .models` defines a second, different hierarchy that is also called `Symbol`,
# `ModuleSymbol`, `ClassSymbol`, `FunctionSymbol`, and for a long time the two
# were imported under the same names in the same modules. The result was
# `isinstance()` checks that could never match: `summary_context` and
# `summary_pipeline` tested persisted symbols against these extracted classes,
# so whole branches of prompt construction never ran and nothing reported it.
# Two hierarchies that cannot share a name cannot repeat that.
from .symbols import (
    ClassSymbol as ExtractedClassSymbol,
    FunctionSymbol as ExtractedFunctionSymbol,
    ModuleSymbol as ExtractedModuleSymbol,
    Parameter,
    Symbol as ExtractedSymbol,
)

__all__ = [
    "AST",
    "ASTNode",
    "CallRelation",
    "ExtractedClassSymbol",
    "ExtractedFunctionSymbol",
    "ExtractedModuleSymbol",
    "ExtractedSymbol",
    "FileSymbolInventory",
    "GoParser",
    "ImportRecord",
    "InheritanceRelation",
    "JavaParser",
    "JavaScriptParser",
    "Parameter",
    "ParseError",
    "ParseFailure",
    "ParseResult",
    "Parser",
    "ParserUnavailableError",
    "Point",
    "PythonParser",
    "RustParser",
    "SUPPORTED_LANGUAGES",
    "SourceFile",
    "SymbolExtractor",
    "TypeScriptParser",
    "UnsupportedLanguageError",
    "extract_symbols",
    "get_parser",
    "parse_batch",
    "parse_source_file",
    "register_parser",
]
