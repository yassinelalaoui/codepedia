"""The symbols as *extracted from source*, before anything is persisted.

This is not the only `Symbol` hierarchy in the project, and the difference
matters. `repository_metadata.models` defines a second one with the same class
names, and the two are not interchangeable:

* here - abstract (`symbol_type`), no `sourceFileId`, no `kind`, no `metadata`.
  A parser produces these while walking a file, before a source-file row exists
  to point at. `parser_engine` sits below persistence and must stay that way.
* `repository_metadata.models` - `sourceFileId`, `kind`, `metadata`,
  `summaryContextHash`, `summaryIsStale`. What a `SourceFileBundle` carries, and
  what every consumer downstream of the store actually holds.

The translation happens in exactly one place:
`repository_metadata.sqlite_store._convert_module_symbol` and its two siblings.

These classes are exported from `parser_engine` only as `ExtractedSymbol`,
`ExtractedModuleSymbol`, `ExtractedClassSymbol` and `ExtractedFunctionSymbol`.
The short names are package-internal, because importing both hierarchies under
the same names is what once left `summary_context._symbol_metadata` and
`summary_pipeline._symbol_source_text` full of `isinstance()` branches that
could never be true.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type: str | None = None
    defaultValue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Symbol(ABC):
    id: str
    name: str
    lineStart: int
    lineEnd: int
    docstring: str = ""
    generatedSummary: str = ""

    def __post_init__(self) -> None:
        if self.lineStart < 1 or self.lineEnd < 1:
            raise ValueError("symbol line positions must be positive")
        if self.lineStart > self.lineEnd:
            raise ValueError("symbol lineStart must be <= lineEnd")

    @property
    @abstractmethod
    def symbol_type(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ModuleSymbol(Symbol):
    filePath: str = ""
    imports: tuple[Any, ...] = field(default_factory=tuple)

    @property
    def symbol_type(self) -> str:
        return "module"


@dataclass(frozen=True, slots=True)
class ClassSymbol(Symbol):
    parentClass: str | None = None
    methods: tuple[Any, ...] = field(default_factory=tuple)
    nestedSymbols: tuple[Any, ...] = field(default_factory=tuple)

    @property
    def symbol_type(self) -> str:
        return "class"


@dataclass(frozen=True, slots=True)
class FunctionSymbol(Symbol):
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)
    returnType: str | None = None
    nestedSymbols: tuple[Any, ...] = field(default_factory=tuple)
    owner: str = "module"
    decorators: tuple[str, ...] = field(default_factory=tuple)

    @property
    def symbol_type(self) -> str:
        return "function"

