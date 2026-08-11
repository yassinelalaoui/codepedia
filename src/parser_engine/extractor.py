from __future__ import annotations

import ast as pyast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .inventory import CallRelation, FileSymbolInventory, ImportRecord, InheritanceRelation
from .models import AST, SourceFile
from .symbols import ClassSymbol, FunctionSymbol, ModuleSymbol, Parameter, Symbol


PYTHON_LANG = "python"
BRACE_LANGUAGES = {"javascript", "typescript", "java", "go", "rust"}


@dataclass(slots=True)
class SymbolExtractor:
    def extract(self, source_file: SourceFile, ast: AST | None = None) -> FileSymbolInventory:
        language = _normalize_language(source_file.language)
        text = source_file.read_text()
        if language == PYTHON_LANG:
            return _extract_python_inventory(source_file=source_file, text=text)
        if language in BRACE_LANGUAGES:
            return _extract_brace_inventory(source_file=source_file, text=text, language=language)
        return _extract_generic_inventory(source_file=source_file, text=text)

    def extract_many(self, source_files: Iterable[SourceFile]) -> list[FileSymbolInventory]:
        return [self.extract(source_file) for source_file in source_files]


def extract_symbols(source_file: SourceFile, ast: AST | None = None) -> FileSymbolInventory:
    return SymbolExtractor().extract(source_file, ast=ast)


def _normalize_language(language: str) -> str:
    value = language.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if value in {"py", "python"}:
        return PYTHON_LANG
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


def _stable_id(prefix: str, source_path: str, name: str, line_start: int, line_end: int, extra: str = "") -> str:
    seed = f"{source_path}|{prefix}|{name}|{line_start}|{line_end}|{extra}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _split_lines(text: str) -> list[str]:
    return text.splitlines()


def _line_span(text: str) -> int:
    return max(1, len(text.splitlines()) or 1)


def _source_slice(text: str, start_line: int, end_line: int) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    start_index = max(0, start_line - 1)
    end_index = min(len(lines), end_line)
    return "\n".join(lines[start_index:end_index]).strip()


def _source_segment(text: str, node: Any) -> str:
    try:
        segment = pyast.get_source_segment(text, node)
    except Exception:
        segment = None
    return segment.strip() if segment else ""


def _line_number(node: Any, attr: str, fallback: int) -> int:
    value = getattr(node, attr, None)
    if isinstance(value, int) and value > 0:
        return value
    return fallback


def _python_unparse(node: Any) -> str:
    if node is None:
        return ""
    try:
        return pyast.unparse(node)
    except Exception:
        return getattr(node, "id", None) or getattr(node, "attr", None) or ""


def _python_docstring(node: pyast.AST) -> str:
    value = pyast.get_docstring(node, clean=True)
    return value or ""


def _python_parameters(node: pyast.FunctionDef | pyast.AsyncFunctionDef) -> tuple[Parameter, ...]:
    args = list(getattr(node.args, "posonlyargs", [])) + list(node.args.args)
    defaults = [None] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
    params: list[Parameter] = []
    for arg, default in zip(args, defaults, strict=False):
        params.append(
            Parameter(
                name=arg.arg,
                type=_python_unparse(arg.annotation) if getattr(arg, "annotation", None) else None,
                defaultValue=_python_unparse(default) if default is not None else None,
            )
        )
    if node.args.vararg is not None:
        params.append(
            Parameter(
                name=f"*{node.args.vararg.arg}",
                type=_python_unparse(node.args.vararg.annotation) if getattr(node.args.vararg, "annotation", None) else None,
            )
        )
    for kwarg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
        params.append(
            Parameter(
                name=kwarg.arg,
                type=_python_unparse(kwarg.annotation) if getattr(kwarg, "annotation", None) else None,
                defaultValue=_python_unparse(default) if default is not None else None,
            )
        )
    if node.args.kwarg is not None:
        params.append(
            Parameter(
                name=f"**{node.args.kwarg.arg}",
                type=_python_unparse(node.args.kwarg.annotation) if getattr(node.args.kwarg, "annotation", None) else None,
            )
        )
    return tuple(params)


def _python_callee_name(call_node: pyast.Call) -> str | None:
    name = _python_unparse(call_node.func)
    return name or None


def _python_collect_calls(
    node: pyast.AST,
    *,
    caller_symbol_id: str,
    source_path: str,
    text: str,
    call_relations: list[CallRelation],
) -> None:
    if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef, pyast.ClassDef)):
        return
    if isinstance(node, pyast.Call):
        callee = _python_callee_name(node)
        start = _line_number(node, "lineno", 1)
        end = _line_number(node, "end_lineno", start)
        call_relations.append(
            CallRelation(
                id=_stable_id("call", source_path, callee or "call", start, end, caller_symbol_id),
                sourceFile=source_path,
                callerSymbolId=caller_symbol_id,
                calleeSymbolIdOrName=callee,
                lineStart=start,
                lineEnd=end,
            )
        )
    for child in pyast.iter_child_nodes(node):
        _python_collect_calls(
            child,
            caller_symbol_id=caller_symbol_id,
            source_path=source_path,
            text=text,
            call_relations=call_relations,
        )


@dataclass(slots=True)
class _PythonBuildResult:
    symbol: Symbol
    classes: list[ClassSymbol] = field(default_factory=list)
    functions: list[FunctionSymbol] = field(default_factory=list)
    imports: list[ImportRecord] = field(default_factory=list)
    calls: list[CallRelation] = field(default_factory=list)
    inheritance: list[InheritanceRelation] = field(default_factory=list)


def _extract_python_inventory(*, source_file: SourceFile, text: str) -> FileSymbolInventory:
    tree = pyast.parse(text, filename=str(source_file.path), type_comments=True)
    source_path = str(source_file.path)
    imports: list[ImportRecord] = []
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.Import, pyast.ImportFrom)):
            start = _line_number(node, "lineno", 1)
            end = _line_number(node, "end_lineno", start)
            snippet = _source_slice(text, start, end)
            imports.append(
                ImportRecord(
                    id=_stable_id("import", source_path, snippet or "import", start, end),
                    sourceFile=source_path,
                    text=snippet,
                    lineStart=start,
                    lineEnd=end,
                )
            )
    result = _python_build_module(
        tree,
        source_path=source_path,
        text=text,
        module_id=_stable_id("module", source_path, Path(source_path).name, 1, _line_span(text)),
        imports=imports,
    )
    module = ModuleSymbol(
        id=result.symbol.id,
        name=Path(source_path).stem,
        lineStart=1,
        lineEnd=_line_span(text),
        docstring=_python_docstring(tree),
        generatedSummary="",
        filePath=source_path,
        imports=tuple(imports),
    )
    return FileSymbolInventory(
        sourceFile=source_path,
        module=module,
        classes=tuple(result.classes),
        functions=tuple(result.functions),
        imports=tuple(imports),
        callRelations=tuple(result.calls),
        inheritanceRelations=tuple(result.inheritance),
    )


def _python_build_module(
    tree: pyast.Module,
    *,
    source_path: str,
    text: str,
    module_id: str,
    imports: list[ImportRecord],
) -> _PythonBuildResult:
    classes: list[ClassSymbol] = []
    functions: list[FunctionSymbol] = []
    calls: list[CallRelation] = []
    inheritance: list[InheritanceRelation] = []

    def build_class(node: pyast.ClassDef) -> _PythonBuildResult:
        line_start = _line_number(node, "lineno", 1)
        line_end = _line_number(node, "end_lineno", line_start)
        parent_class = ", ".join(filter(None, (_python_unparse(base) for base in node.bases))) or None
        class_id = _stable_id("class", source_path, node.name, line_start, line_end, parent_class or "")
        methods: list[FunctionSymbol] = []
        nested_symbols: list[Symbol] = []
        nested_classes: list[ClassSymbol] = []
        class_calls: list[CallRelation] = []
        class_inheritance: list[InheritanceRelation] = []
        for base in node.bases:
            base_name = _python_unparse(base)
            if base_name:
                class_inheritance.append(
                    InheritanceRelation(
                        id=_stable_id("inherit", source_path, node.name, line_start, line_end, base_name),
                        sourceFile=source_path,
                        subclassSymbolId=class_id,
                        parentClassName=base_name,
                        lineStart=line_start,
                        lineEnd=line_end,
                    )
                )
        for stmt in node.body:
            if isinstance(stmt, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
                function_result = build_function(stmt, owner="class", parent_symbol_id=class_id)
                methods.append(function_result.symbol)  # type: ignore[arg-type]
                functions.append(function_result.symbol)  # type: ignore[arg-type]
                functions.extend(function_result.functions)
                nested_classes.extend(function_result.classes)
                class_calls.extend(function_result.calls)
                class_inheritance.extend(function_result.inheritance)
                continue
            if isinstance(stmt, pyast.ClassDef):
                nested_class_result = build_class(stmt)
                nested_classes.append(nested_class_result.symbol)  # type: ignore[arg-type]
                classes.append(nested_class_result.symbol)  # type: ignore[arg-type]
                classes.extend(nested_class_result.classes)
                functions.extend(nested_class_result.functions)
                class_calls.extend(nested_class_result.calls)
                class_inheritance.extend(nested_class_result.inheritance)
                nested_symbols.append(nested_class_result.symbol)
                continue
            _python_collect_calls(stmt, caller_symbol_id=class_id, source_path=source_path, text=text, call_relations=class_calls)
        class_symbol = ClassSymbol(
            id=class_id,
            name=node.name,
            lineStart=line_start,
            lineEnd=line_end,
            docstring=_python_docstring(node),
            generatedSummary="",
            parentClass=parent_class,
            methods=tuple(methods),
            nestedSymbols=tuple(nested_symbols),
        )
        return _PythonBuildResult(
            symbol=class_symbol,
            classes=nested_classes,
            functions=[],
            imports=[],
            calls=class_calls,
            inheritance=class_inheritance,
        )

    def build_function(
        node: pyast.FunctionDef | pyast.AsyncFunctionDef,
        *,
        owner: str,
        parent_symbol_id: str,
    ) -> _PythonBuildResult:
        line_start = _line_number(node, "lineno", 1)
        line_end = _line_number(node, "end_lineno", line_start)
        function_id = _stable_id("function", source_path, node.name, line_start, line_end, parent_symbol_id)
        nested_symbols: list[Symbol] = []
        nested_functions: list[FunctionSymbol] = []
        nested_classes: list[ClassSymbol] = []
        function_calls: list[CallRelation] = []
        function_inheritance: list[InheritanceRelation] = []
        for stmt in node.body:
            if isinstance(stmt, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
                nested_result = build_function(stmt, owner="module", parent_symbol_id=function_id)
                nested_functions.append(nested_result.symbol)  # type: ignore[arg-type]
                nested_functions.extend(nested_result.functions)
                nested_classes.extend(nested_result.classes)
                function_calls.extend(nested_result.calls)
                function_inheritance.extend(nested_result.inheritance)
                nested_symbols.append(nested_result.symbol)
                continue
            if isinstance(stmt, pyast.ClassDef):
                nested_class_result = build_class(stmt)
                nested_classes.append(nested_class_result.symbol)  # type: ignore[arg-type]
                classes.append(nested_class_result.symbol)  # type: ignore[arg-type]
                classes.extend(nested_class_result.classes)
                functions.extend(nested_class_result.functions)
                function_calls.extend(nested_class_result.calls)
                function_inheritance.extend(nested_class_result.inheritance)
                nested_symbols.append(nested_class_result.symbol)
                continue
            _python_collect_calls(stmt, caller_symbol_id=function_id, source_path=source_path, text=text, call_relations=function_calls)
        function_symbol = FunctionSymbol(
            id=function_id,
            name=node.name,
            lineStart=line_start,
            lineEnd=line_end,
            docstring=_python_docstring(node),
            generatedSummary="",
            parameters=_python_parameters(node),
            returnType=_python_unparse(node.returns) if getattr(node, "returns", None) else None,
            nestedSymbols=tuple(nested_symbols),
            owner=owner,
        )
        return _PythonBuildResult(
            symbol=function_symbol,
            classes=nested_classes,
            functions=nested_functions,
            imports=[],
            calls=function_calls,
            inheritance=function_inheritance,
        )

    for stmt in tree.body:
        if isinstance(stmt, pyast.ClassDef):
            class_result = build_class(stmt)
            classes.append(class_result.symbol)  # type: ignore[arg-type]
            classes.extend(class_result.classes)
            functions.extend(class_result.functions)
            calls.extend(class_result.calls)
            inheritance.extend(class_result.inheritance)
            continue
        if isinstance(stmt, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
            function_result = build_function(stmt, owner="module", parent_symbol_id=module_id)
            functions.append(function_result.symbol)  # type: ignore[arg-type]
            functions.extend(function_result.functions)
            classes.extend(function_result.classes)
            calls.extend(function_result.calls)
            inheritance.extend(function_result.inheritance)
            continue
        _python_collect_calls(stmt, caller_symbol_id=module_id, source_path=source_path, text=text, call_relations=calls)

    return _PythonBuildResult(
        symbol=ModuleSymbol(id=module_id, name=Path(source_path).stem, lineStart=1, lineEnd=_line_span(text)),
        classes=classes,
        functions=functions,
        imports=imports,
        calls=calls,
        inheritance=inheritance,
    )


@dataclass(slots=True)
class _DeclaredItem:
    kind: str
    name: str
    start_line: int
    end_line: int
    parent_class: str | None = None
    parameters: tuple[Parameter, ...] = field(default_factory=tuple)
    return_type: str | None = None
    owner: str = "module"
    receiver: str | None = None
    docstring: str = ""
    line_text: str = ""
    methods: list[int] = field(default_factory=list)
    nested: list[int] = field(default_factory=list)
    parent_index: int | None = None
    symbol: Symbol | None = None


def _extract_brace_inventory(*, source_file: SourceFile, text: str, language: str) -> FileSymbolInventory:
    lines = _split_lines(text)
    source_path = str(source_file.path)
    items = _scan_brace_declarations(text=text, language=language, lines=lines)
    _assign_brace_parents(items)
    classes: list[ClassSymbol] = []
    functions: list[FunctionSymbol] = []
    calls: list[CallRelation] = []
    inheritance: list[InheritanceRelation] = []
    imports = _extract_brace_imports(source_path=source_path, language=language, lines=lines)
    item_to_symbol: dict[int, Symbol] = {}
    for index, item in enumerate(items):
        if item.kind == "class":
            symbol = ClassSymbol(
                id=_stable_id("class", source_path, item.name, item.start_line, item.end_line, item.parent_class or ""),
                name=item.name,
                lineStart=item.start_line,
                lineEnd=item.end_line,
                docstring=item.docstring,
                generatedSummary="",
                parentClass=item.parent_class,
            )
            item.symbol = symbol
            classes.append(symbol)
            item_to_symbol[index] = symbol
        elif item.kind == "function":
            symbol = FunctionSymbol(
                id=_stable_id("function", source_path, item.name, item.start_line, item.end_line, item.parent_class or item.owner),
                name=item.name,
                lineStart=item.start_line,
                lineEnd=item.end_line,
                docstring=item.docstring,
                generatedSummary="",
                parameters=item.parameters,
                returnType=item.return_type,
                owner=item.owner,
            )
            item.symbol = symbol
            functions.append(symbol)
            item_to_symbol[index] = symbol
    _attach_brace_relationships(items, item_to_symbol)
    for item in items:
        if isinstance(item.symbol, ClassSymbol) and item.parent_class:
            inheritance.append(
                InheritanceRelation(
                    id=_stable_id("inherit", source_path, item.name, item.start_line, item.end_line, item.parent_class),
                    sourceFile=source_path,
                    subclassSymbolId=item.symbol.id,
                    parentClassName=item.parent_class,
                    lineStart=item.start_line,
                    lineEnd=item.end_line,
                )
            )
    module = ModuleSymbol(
        id=_stable_id("module", source_path, Path(source_path).name, 1, max(1, len(lines))),
        name=Path(source_path).stem,
        lineStart=1,
        lineEnd=max(1, len(lines)),
        docstring=_leading_docstring(lines, language),
        generatedSummary="",
        filePath=source_path,
        imports=tuple(imports),
    )
    _collect_brace_calls(lines=lines, items=items, source_path=source_path, language=language, module_id=module.id, calls=calls)
    return FileSymbolInventory(
        sourceFile=source_path,
        module=module,
        classes=tuple(classes),
        functions=tuple(functions),
        imports=tuple(imports),
        callRelations=tuple(calls),
        inheritanceRelations=tuple(inheritance),
    )


def _extract_generic_inventory(*, source_file: SourceFile, text: str) -> FileSymbolInventory:
    source_path = str(source_file.path)
    module = ModuleSymbol(
        id=_stable_id("module", source_path, Path(source_path).name, 1, _line_span(text)),
        name=Path(source_path).stem,
        lineStart=1,
        lineEnd=_line_span(text),
        docstring="",
        generatedSummary="",
        filePath=source_path,
        imports=(),
    )
    return FileSymbolInventory(
        sourceFile=source_path,
        module=module,
        classes=(),
        functions=(),
        imports=(),
        callRelations=(),
        inheritanceRelations=(),
    )


def _extract_brace_imports(*, source_path: str, language: str, lines: list[str]) -> list[ImportRecord]:
    imports: list[ImportRecord] = []
    if language == "go":
        in_block = False
        block_start = 0
        block_lines: list[str] = []
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("import ("):
                in_block = True
                block_start = line_no
                block_lines = [line]
                continue
            if in_block:
                block_lines.append(line)
                if stripped == ")":
                    text = "\n".join(block_lines).strip()
                    imports.append(
                        ImportRecord(
                            id=_stable_id("import", source_path, text, block_start, line_no),
                            sourceFile=source_path,
                            text=text,
                            lineStart=block_start,
                            lineEnd=line_no,
                        )
                    )
                    in_block = False
                    block_lines = []
                continue
            if stripped.startswith("import "):
                imports.append(
                    ImportRecord(
                        id=_stable_id("import", source_path, stripped, line_no, line_no),
                        sourceFile=source_path,
                        text=stripped,
                        lineStart=line_no,
                        lineEnd=line_no,
                    )
                )
        return imports
    patterns = {
        "javascript": [re.compile(r"^\s*import\s+.+"), re.compile(r"^\s*export\s+.*from\s+['\"].+['\"]\s*;?")],
        "typescript": [re.compile(r"^\s*import\s+.+"), re.compile(r"^\s*export\s+.*from\s+['\"].+['\"]\s*;?")],
        "java": [re.compile(r"^\s*import\s+[^;]+;")],
        "rust": [re.compile(r"^\s*use\s+[^;]+;"), re.compile(r"^\s*extern\s+crate\s+[^;]+;")],
    }.get(language, [])
    for line_no, line in enumerate(lines, start=1):
        if any(pattern.match(line) for pattern in patterns):
            stripped = line.strip()
            imports.append(
                ImportRecord(
                    id=_stable_id("import", source_path, stripped, line_no, line_no),
                    sourceFile=source_path,
                    text=stripped,
                    lineStart=line_no,
                    lineEnd=line_no,
                )
            )
    return imports


def _scan_brace_declarations(*, text: str, language: str, lines: list[str]) -> list[_DeclaredItem]:
    items: list[_DeclaredItem] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        class_match = next((match for pattern in _class_patterns(language) if (match := pattern.match(line))), None)
        if class_match is not None:
            parent = class_match.groupdict().get("parent")
            parent2 = class_match.groupdict().get("parent2")
            parent_class = _normalize_type_text(parent2 or parent)
            start_line = line_no
            end_line = _find_block_end(lines, start_line)
            items.append(
                _DeclaredItem(
                    kind="class",
                    name=class_match.group("name"),
                    start_line=start_line,
                    end_line=end_line,
                    parent_class=parent_class,
                    docstring=_leading_docstring(lines[: start_line - 1], language),
                    line_text=line,
                )
            )
            continue
        function_match = next((match for pattern in _function_patterns(language) if (match := pattern.match(line))), None)
        if function_match is not None:
            parameters, return_type, owner, receiver = _parse_function_signature(language, function_match)
            start_line = line_no
            end_line = _find_block_end(lines, start_line)
            items.append(
                _DeclaredItem(
                    kind="function",
                    name=function_match.group("name"),
                    start_line=start_line,
                    end_line=end_line,
                    parameters=parameters,
                    return_type=return_type,
                    owner=owner,
                    receiver=receiver,
                    docstring=_leading_docstring(lines[: start_line - 1], language),
                    line_text=line,
                )
            )
    return items


def _assign_brace_parents(items: list[_DeclaredItem]) -> None:
    ordered = sorted(range(len(items)), key=lambda index: (items[index].start_line, -(items[index].end_line - items[index].start_line), index))
    for index in ordered:
        item = items[index]
        parent_index: int | None = None
        for candidate_index in ordered:
            if candidate_index == index:
                continue
            candidate = items[candidate_index]
            if candidate.start_line <= item.start_line and candidate.end_line >= item.end_line:
                if parent_index is None:
                    parent_index = candidate_index
                else:
                    current = items[parent_index]
                    current_span = current.end_line - current.start_line
                    candidate_span = candidate.end_line - candidate.start_line
                    if candidate_span < current_span:
                        parent_index = candidate_index
        item.parent_index = parent_index
    for index, item in enumerate(items):
        parent_index = item.parent_index
        if parent_index is None:
            continue
        parent = items[parent_index]
        if parent.kind == "class" and item.kind == "function":
            item.owner = "class"
            parent.methods.append(index)
        else:
            parent.nested.append(index)


def _attach_brace_relationships(items: list[_DeclaredItem], item_to_symbol: dict[int, Symbol]) -> None:
    for index, item in enumerate(items):
        symbol = item.symbol
        if symbol is None:
            continue
        if isinstance(symbol, ClassSymbol):
            methods: list[FunctionSymbol] = []
            nested_symbols: list[Symbol] = []
            for child_index in item.methods:
                child_symbol = item_to_symbol.get(child_index)
                if isinstance(child_symbol, FunctionSymbol):
                    methods.append(child_symbol)
            for child_index in item.nested:
                child_symbol = item_to_symbol.get(child_index)
                if child_symbol is not None:
                    nested_symbols.append(child_symbol)
            item.symbol = ClassSymbol(
                id=symbol.id,
                name=symbol.name,
                lineStart=symbol.lineStart,
                lineEnd=symbol.lineEnd,
                docstring=symbol.docstring,
                generatedSummary=symbol.generatedSummary,
                parentClass=symbol.parentClass,
                methods=tuple(methods),
                nestedSymbols=tuple(nested_symbols),
            )
            item_to_symbol[index] = item.symbol
        elif isinstance(symbol, FunctionSymbol):
            nested_symbols: list[Symbol] = []
            for child_index in item.nested:
                child_symbol = item_to_symbol.get(child_index)
                if child_symbol is not None:
                    nested_symbols.append(child_symbol)
            item.symbol = FunctionSymbol(
                id=symbol.id,
                name=symbol.name,
                lineStart=symbol.lineStart,
                lineEnd=symbol.lineEnd,
                docstring=symbol.docstring,
                generatedSummary=symbol.generatedSummary,
                parameters=symbol.parameters,
                returnType=symbol.returnType,
                nestedSymbols=tuple(nested_symbols),
                owner=symbol.owner,
            )
            item_to_symbol[index] = item.symbol


def _collect_brace_calls(
    *,
    lines: list[str],
    items: list[_DeclaredItem],
    source_path: str,
    language: str,
    module_id: str,
    calls: list[CallRelation],
) -> None:
    all_spans = [(item.start_line, item.end_line) for item in items]

    def collect_for_range(start_line: int, end_line: int, caller_id: str, excluded: list[tuple[int, int]]) -> None:
        for line_no in range(start_line, end_line + 1):
            if _line_in_spans(line_no, excluded):
                continue
            line = lines[line_no - 1]
            if _looks_like_declaration(line, language):
                continue
            for callee in _call_matches(line, language):
                calls.append(
                    CallRelation(
                        id=_stable_id("call", source_path, callee or "call", line_no, line_no, caller_id),
                        sourceFile=source_path,
                        callerSymbolId=caller_id,
                        calleeSymbolIdOrName=callee,
                        lineStart=line_no,
                        lineEnd=line_no,
                    )
                )

    collect_for_range(1, max(1, len(lines)), module_id, all_spans)
    for item in items:
        if item.symbol is None:
            continue
        child_spans = [(items[child_index].start_line, items[child_index].end_line) for child_index in item.methods + item.nested if child_index < len(items)]
        collect_for_range(item.start_line, item.end_line, item.symbol.id, child_spans)


def _class_patterns(language: str) -> list[re.Pattern[str]]:
    if language in {"javascript", "typescript"}:
        return [re.compile(r"^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+(?P<parent>[^{]+))?\s*\{")]
    if language == "java":
        return [
            re.compile(
                r"^\s*(?:public|protected|private|abstract|final|static|\s)*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+(?P<parent>[A-Za-z_][A-Za-z0-9_\.]*))?(?:\s+implements\s+(?P<parent2>[^{]+))?\s*\{"
            )
        ]
    if language == "go":
        return [re.compile(r"^\s*type\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+struct\b"), re.compile(r"^\s*type\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+interface\b")]
    if language == "rust":
        return [
            re.compile(r"^\s*(?:pub\s+)?struct\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[\{;]"),
            re.compile(r"^\s*(?:pub\s+)?enum\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{"),
            re.compile(r"^\s*(?:pub\s+)?trait\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{"),
        ]
    return []


def _function_patterns(language: str) -> list[re.Pattern[str]]:
    if language in {"javascript", "typescript"}:
        return [
            re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?::\s*(?P<return>[^{}=>]+))?\s*\{"),
            re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?::\s*(?P<return>[^{}=>]+))?\s*\{"),
        ]
    if language == "java":
        return [
            re.compile(r"^\s*(?:public|protected|private|static|final|abstract|synchronized|native|\s)+(?P<return>[A-Za-z_][A-Za-z0-9_<>\[\].? ]*)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?:throws\s+[^{]+)?\s*\{"),
            re.compile(r"^\s*(?:public|protected|private)?\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*\{"),
        ]
    if language == "go":
        return [re.compile(r"^\s*func\s+(?:(?P<receiver>\([^)]*\))\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?P<return>(?:\([^)]*\)|[^{]+))?\s*\{")]
    if language == "rust":
        return [re.compile(r"^\s*(?:pub\s+)?fn\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>[^)]*)\)\s*(?:->\s*(?P<return>[^{]+))?\s*\{")]
    return []


def _parse_function_signature(language: str, match: re.Match[str]) -> tuple[tuple[Parameter, ...], str | None, str, str | None]:
    params_text = (match.groupdict().get("params") or "").strip()
    return_text = (match.groupdict().get("return") or "").strip() or None
    receiver = (match.groupdict().get("receiver") or "").strip() or None
    owner = "class" if receiver else "module"
    parameters = tuple(_parse_parameters(params_text, language))
    return parameters, _normalize_type_text(return_text), owner, _receiver_name(receiver)


def _receiver_name(receiver: str | None) -> str | None:
    if not receiver:
        return None
    match = re.search(r"\(\s*(?:[*&]\s*)?(?:[A-Za-z_][A-Za-z0-9_]*\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:[*&])?\s*\)", receiver)
    if match:
        return match.group("name")
    return None


def _parse_parameters(params_text: str, language: str) -> list[Parameter]:
    if not params_text.strip():
        return []
    parameters: list[Parameter] = []
    for raw_item in _split_arguments(params_text):
        item = raw_item.strip()
        if not item:
            continue
        name = item
        annotation: str | None = None
        default_value: str | None = None
        if language in {"javascript", "typescript"}:
            if "=" in item:
                before, after = [part.strip() for part in item.split("=", 1)]
                default_value = after
                item = before
            if ":" in item:
                name, annotation = [part.strip() for part in item.split(":", 1)]
            else:
                name = item
        elif language == "java":
            parts = item.rsplit(" ", 1)
            if len(parts) == 2:
                annotation, name = parts[0].strip(), parts[1].strip()
        elif language in {"go", "rust"}:
            if ":" in item:
                name, annotation = [part.strip() for part in item.split(":", 1)]
            elif " " in item:
                name, annotation = [part.strip() for part in item.split(" ", 1)]
        else:
            if ":" in item:
                name, annotation = [part.strip() for part in item.split(":", 1)]
        parameters.append(Parameter(name=name.lstrip("*&"), type=_normalize_type_text(annotation), defaultValue=_normalize_type_text(default_value)))
    return parameters


def _split_arguments(params_text: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    depth = 0
    for char in params_text:
        if char == "," and depth == 0:
            result.append("".join(current))
            current = []
            continue
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth = max(0, depth - 1)
        current.append(char)
    if current:
        result.append("".join(current))
    return result


def _normalize_type_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip(",")
    return cleaned or None


def _leading_docstring(lines: list[str], language: str) -> str:
    if not lines:
        return ""
    collected: list[str] = []
    index = len(lines) - 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            if collected:
                break
            index -= 1
            continue
        if language == "python" and (stripped.startswith('"""') or stripped.startswith("'''")):
            collected.append(stripped.strip("\"'"))
            break
        if stripped.startswith("//") or stripped.startswith("#"):
            collected.append(stripped.lstrip("/#").strip())
            index -= 1
            continue
        if stripped.startswith("/*") or stripped.startswith("*"):
            collected.append(stripped.lstrip("/*").rstrip("*/").strip())
            index -= 1
            continue
        break
    return "\n".join(reversed([item for item in collected if item]))


def _find_block_end(lines: list[str], start_line: int) -> int:
    open_braces = 0
    seen_open = False
    for line_no in range(start_line, len(lines) + 1):
        line = lines[line_no - 1]
        for char in line:
            if char == "{":
                open_braces += 1
                seen_open = True
            elif char == "}":
                if seen_open:
                    open_braces -= 1
                    if open_braces <= 0:
                        return line_no
    return start_line


def _line_in_spans(line_no: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= line_no <= end for start, end in spans)


def _looks_like_declaration(line: str, language: str) -> bool:
    return any(pattern.match(line) for pattern in _class_patterns(language) + _function_patterns(language))


def _call_matches(line: str, language: str) -> list[str | None]:
    if language not in {"javascript", "typescript", "java", "go", "rust"}:
        return []
    candidates: list[str | None] = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", line):
        name = match.group(1)
        if name in {"if", "for", "while", "switch", "catch", "return", "new", "func", "class", "fn"}:
            continue
        candidates.append(name)
    return candidates


def _extract_brace_imports(*, source_path: str, language: str, lines: list[str]) -> list[ImportRecord]:
    imports: list[ImportRecord] = []
    if language == "go":
        in_block = False
        block_start = 0
        block_lines: list[str] = []
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("import ("):
                in_block = True
                block_start = line_no
                block_lines = [line]
                continue
            if in_block:
                block_lines.append(line)
                if stripped == ")":
                    text = "\n".join(block_lines).strip()
                    imports.append(
                        ImportRecord(
                            id=_stable_id("import", source_path, text, block_start, line_no),
                            sourceFile=source_path,
                            text=text,
                            lineStart=block_start,
                            lineEnd=line_no,
                        )
                    )
                    in_block = False
                    block_lines = []
                continue
            if stripped.startswith("import "):
                imports.append(
                    ImportRecord(
                        id=_stable_id("import", source_path, stripped, line_no, line_no),
                        sourceFile=source_path,
                        text=stripped,
                        lineStart=line_no,
                        lineEnd=line_no,
                    )
                )
        return imports
    patterns = {
        "javascript": [re.compile(r"^\s*import\s+.+"), re.compile(r"^\s*export\s+.*from\s+['\"].+['\"]\s*;?")],
        "typescript": [re.compile(r"^\s*import\s+.+"), re.compile(r"^\s*export\s+.*from\s+['\"].+['\"]\s*;?")],
        "java": [re.compile(r"^\s*import\s+[^;]+;")],
        "rust": [re.compile(r"^\s*use\s+[^;]+;"), re.compile(r"^\s*extern\s+crate\s+[^;]+;")],
    }.get(language, [])
    for line_no, line in enumerate(lines, start=1):
        if any(pattern.match(line) for pattern in patterns):
            stripped = line.strip()
            imports.append(
                ImportRecord(
                    id=_stable_id("import", source_path, stripped, line_no, line_no),
                    sourceFile=source_path,
                    text=stripped,
                    lineStart=line_no,
                    lineEnd=line_no,
                )
            )
    return imports


def _scan_brace_declarations(*, text: str, language: str, lines: list[str]) -> list[_DeclaredItem]:
    items: list[_DeclaredItem] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        class_match = next((match for pattern in _class_patterns(language) if (match := pattern.match(line))), None)
        if class_match is not None:
            parent = class_match.groupdict().get("parent")
            parent2 = class_match.groupdict().get("parent2")
            parent_class = _normalize_type_text(parent2 or parent)
            items.append(
                _DeclaredItem(
                    kind="class",
                    name=class_match.group("name"),
                    start_line=line_no,
                    end_line=_find_block_end(lines, line_no),
                    parent_class=parent_class,
                    docstring=_leading_docstring(lines[: line_no - 1], language),
                    line_text=line,
                )
            )
            continue
        function_match = next((match for pattern in _function_patterns(language) if (match := pattern.match(line))), None)
        if function_match is not None:
            parameters, return_type, owner, receiver = _parse_function_signature(language, function_match)
            items.append(
                _DeclaredItem(
                    kind="function",
                    name=function_match.group("name"),
                    start_line=line_no,
                    end_line=_find_block_end(lines, line_no),
                    parameters=parameters,
                    return_type=return_type,
                    owner=owner,
                    receiver=receiver,
                    docstring=_leading_docstring(lines[: line_no - 1], language),
                    line_text=line,
                )
            )
    return items


def _assign_brace_parents(items: list[_DeclaredItem]) -> None:
    ordered = sorted(range(len(items)), key=lambda index: (items[index].start_line, -(items[index].end_line - items[index].start_line), index))
    for index in ordered:
        item = items[index]
        parent_index: int | None = None
        for candidate_index in ordered:
            if candidate_index == index:
                continue
            candidate = items[candidate_index]
            if candidate.start_line <= item.start_line and candidate.end_line >= item.end_line:
                if parent_index is None:
                    parent_index = candidate_index
                else:
                    current = items[parent_index]
                    if (candidate.end_line - candidate.start_line) < (current.end_line - current.start_line):
                        parent_index = candidate_index
        item.parent_index = parent_index
    for index, item in enumerate(items):
        parent_index = item.parent_index
        if parent_index is None:
            continue
        parent = items[parent_index]
        if parent.kind == "class" and item.kind == "function":
            item.owner = "class"
            parent.methods.append(index)
        else:
            parent.nested.append(index)


def _attach_brace_relationships(items: list[_DeclaredItem], item_to_symbol: dict[int, Symbol]) -> None:
    for index, item in enumerate(items):
        symbol = item.symbol
        if symbol is None:
            continue
        if isinstance(symbol, ClassSymbol):
            methods: list[FunctionSymbol] = []
            nested_symbols: list[Symbol] = []
            for child_index in item.methods:
                child_symbol = item_to_symbol.get(child_index)
                if isinstance(child_symbol, FunctionSymbol):
                    methods.append(child_symbol)
            for child_index in item.nested:
                child_symbol = item_to_symbol.get(child_index)
                if child_symbol is not None:
                    nested_symbols.append(child_symbol)
            item.symbol = ClassSymbol(
                id=symbol.id,
                name=symbol.name,
                lineStart=symbol.lineStart,
                lineEnd=symbol.lineEnd,
                docstring=symbol.docstring,
                generatedSummary=symbol.generatedSummary,
                parentClass=symbol.parentClass,
                methods=tuple(methods),
                nestedSymbols=tuple(nested_symbols),
            )
            item_to_symbol[index] = item.symbol
        elif isinstance(symbol, FunctionSymbol):
            nested_symbols: list[Symbol] = []
            for child_index in item.nested:
                child_symbol = item_to_symbol.get(child_index)
                if child_symbol is not None:
                    nested_symbols.append(child_symbol)
            item.symbol = FunctionSymbol(
                id=symbol.id,
                name=symbol.name,
                lineStart=symbol.lineStart,
                lineEnd=symbol.lineEnd,
                docstring=symbol.docstring,
                generatedSummary=symbol.generatedSummary,
                parameters=symbol.parameters,
                returnType=symbol.returnType,
                nestedSymbols=tuple(nested_symbols),
                owner=symbol.owner,
            )
            item_to_symbol[index] = item.symbol
