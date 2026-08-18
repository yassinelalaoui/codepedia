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

