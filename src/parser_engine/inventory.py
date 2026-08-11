from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .symbols import ClassSymbol, FunctionSymbol, ModuleSymbol


@dataclass(frozen=True, slots=True)
class ImportRecord:
    id: str
    sourceFile: str
    text: str
    lineStart: int
    lineEnd: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CallRelation:
    id: str
    sourceFile: str
    callerSymbolId: str | None
    calleeSymbolIdOrName: str | None
    lineStart: int
    lineEnd: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InheritanceRelation:
    id: str
    sourceFile: str
    subclassSymbolId: str
    parentClassName: str
    lineStart: int
    lineEnd: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FileSymbolInventory:
    sourceFile: str
    module: ModuleSymbol
    classes: tuple[ClassSymbol, ...]
    functions: tuple[FunctionSymbol, ...]
    imports: tuple[ImportRecord, ...]
    callRelations: tuple[CallRelation, ...]
    inheritanceRelations: tuple[InheritanceRelation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceFile": self.sourceFile,
            "module": self.module.to_dict(),
            "classes": [item.to_dict() for item in self.classes],
            "functions": [item.to_dict() for item in self.functions],
            "imports": [item.to_dict() for item in self.imports],
            "callRelations": [item.to_dict() for item in self.callRelations],
            "inheritanceRelations": [item.to_dict() for item in self.inheritanceRelations],
        }

