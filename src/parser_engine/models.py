from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Point:
    row: int
    column: int

    @classmethod
    def from_value(cls, value: Any) -> "Point":
        if hasattr(value, "row") and hasattr(value, "column"):
            return cls(row=int(value.row), column=int(value.column))
        if isinstance(value, tuple) and len(value) >= 2:
            return cls(row=int(value[0]), column=int(value[1]))
        if isinstance(value, list) and len(value) >= 2:
            return cls(row=int(value[0]), column=int(value[1]))
        raise TypeError(f"Unsupported point value: {value!r}")


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    language: str
    content: str | bytes | None = None
    encoding: str = "utf-8"

    def read_text(self) -> str:
        if self.content is None:
            return self.path.read_text(encoding=self.encoding, errors="replace")
        if isinstance(self.content, bytes):
            return self.content.decode(self.encoding, errors="replace")
        return self.content


@dataclass(frozen=True, slots=True)
class ASTNode:
    type: str
    start_byte: int
    end_byte: int
    start_point: Point
    end_point: Point
    children: tuple["ASTNode", ...] = ()
    fields: dict[str, "ASTNode"] = field(default_factory=dict)
    named: bool = True
    extra: bool = False
    missing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "start_point": asdict(self.start_point),
            "end_point": asdict(self.end_point),
            "children": [child.to_dict() for child in self.children],
            "fields": {key: value.to_dict() for key, value in self.fields.items()},
            "named": self.named,
            "extra": self.extra,
            "missing": self.missing,
        }


@dataclass(frozen=True, slots=True)
class AST:
    language: str
    root: ASTNode
    source_path: str
    has_errors: bool = False
    parser_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "root": self.root.to_dict(),
            "source_path": self.source_path,
            "has_errors": self.has_errors,
            "parser_name": self.parser_name,
        }


@dataclass(frozen=True, slots=True)
class ParseFailure:
    source_path: str
    language: str
    parser_name: str
    message: str
    recoverable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ParseResult:
    source_path: str
    language: str
    status: str
    ast: AST | None = None
    failure: ParseFailure | None = None

    @property
    def success(self) -> bool:
        return self.status == "success" and self.ast is not None

    @classmethod
    def from_ast(cls, ast: AST) -> "ParseResult":
        return cls(
            source_path=ast.source_path,
            language=ast.language,
            status="success",
            ast=ast,
            failure=None,
        )

    @classmethod
    def from_failure(cls, failure: ParseFailure) -> "ParseResult":
        return cls(
            source_path=failure.source_path,
            language=failure.language,
            status="failure",
            ast=None,
            failure=failure,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "language": self.language,
            "status": self.status,
            "ast": None if self.ast is None else self.ast.to_dict(),
            "failure": None if self.failure is None else self.failure.to_dict(),
        }

