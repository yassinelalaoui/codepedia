"""Symbol facts read from a tree-sitter AST.

The regex scanner in :mod:`parser_engine.extractor` only ever sees one line at
a time, so it misses everything that spans lines (multi-line signatures,
arrow functions bound to a const, methods of a Rust ``impl`` block) and
mis-attributes nesting. This module walks the real AST produced by the
language parsers and reports the same facts the extractor needs, so the
extractor can build its inventory from a syntax tree and keep the regex
scanner purely as a fallback for files no grammar can parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .models import AST, ASTNode
from .symbols import Parameter

SUPPORTED_LANGUAGES = ("javascript", "typescript", "java", "go", "rust")

_CLASS_NODE_TYPES: dict[str, frozenset[str]] = {
    "javascript": frozenset({"class_declaration"}),
    "typescript": frozenset(
        {"class_declaration", "abstract_class_declaration", "interface_declaration", "enum_declaration"}
    ),
    "java": frozenset(
        {
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "annotation_type_declaration",
        }
    ),
    "go": frozenset({"type_spec"}),
    "rust": frozenset({"struct_item", "enum_item", "trait_item", "union_item"}),
}

_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    "javascript": frozenset({"function_declaration", "generator_function_declaration", "method_definition"}),
    "typescript": frozenset(
        {
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "function_signature",
            "method_signature",
            "abstract_method_signature",
        }
    ),
    "java": frozenset({"method_declaration", "constructor_declaration", "compact_constructor_declaration"}),
    "go": frozenset({"function_declaration", "method_declaration"}),
    "rust": frozenset({"function_item", "function_signature_item"}),
}

_IMPORT_NODE_TYPES: dict[str, frozenset[str]] = {
    "javascript": frozenset({"import_statement"}),
    "typescript": frozenset({"import_statement"}),
    "java": frozenset({"import_declaration"}),
    "go": frozenset({"import_declaration"}),
    "rust": frozenset({"use_declaration", "extern_crate_declaration"}),
}

_PARAMETER_LIST_TYPES = frozenset({"formal_parameters", "parameter_list", "parameters"})
_FUNCTION_VALUE_TYPES = frozenset({"arrow_function", "function", "function_expression", "generator_function"})
_IMPL_TYPES = frozenset({"impl_item"})
_BOUND_FUNCTION_TYPES = frozenset({"variable_declarator", "public_field_definition", "field_definition"})
# Nodes that merely wrap a declaration: a doc comment sits above the
# wrapper, so the declaration inside it has to look one level out.
_WRAPPER_TYPES = frozenset({"type_declaration", "export_statement", "lexical_declaration", "variable_declaration"})
_EXTENDS_PATTERN = re.compile(r"\bextends\s+([A-Za-z_$][\w$.]*)")
_IMPLEMENTS_PATTERN = re.compile(r"\bimplements\s+(.+)", re.DOTALL)
_RECEIVER_PATTERN = re.compile(r"([A-Za-z_]\w*)\s*\)\s*$")


@dataclass(slots=True)
class TSDeclaration:
    kind: str
    name: str
    start_line: int
    end_line: int
    parent_index: int | None = None
    parent_class: str | None = None
    interfaces: tuple[str, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    return_type: str | None = None
    owner: str = "module"
    docstring: str = ""
    impl_type: str | None = None


@dataclass(slots=True)
class TSImport:
    text: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class TSCall:
    name: str
    line: int
    declaration_index: int | None


@dataclass(slots=True)
class TSInheritance:
    type_name: str
    parent_name: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class TSFileFacts:
    declarations: list[TSDeclaration] = field(default_factory=list)
    imports: list[TSImport] = field(default_factory=list)
    calls: list[TSCall] = field(default_factory=list)
    inheritance: list[TSInheritance] = field(default_factory=list)
    module_docstring: str = ""


def supports(language: str) -> bool:
    return language in SUPPORTED_LANGUAGES


def extract_file_facts(*, ast: AST, text: str, language: str) -> TSFileFacts | None:
    """Read declarations, imports, calls and inheritance out of ``ast``.

    Returns ``None`` when the language has no node-type mapping or when the
    AST is an outline built by a regex fallback parser rather than a real
    syntax tree - in both cases the caller should use its own fallback.
    """
    if not supports(language):
        return None
    root = ast.root
    if root.children and all(not child.children for child in root.children):
        # `build_outline_fallback` produces a flat root of childless leaves;
        # walking it adds nothing the regex scanner would not do better.
        return None
    source = text.encode("utf-8", errors="replace")
    walker = _Walker(source=source, language=language)
    walker.visit_children(root, parent_index=None, impl_type=None)
    walker.facts.module_docstring = _module_docstring(root, source)
    return walker.facts


_Outer = tuple[tuple[ASTNode, ...], int, ASTNode]


@dataclass(slots=True)
class _Walker:
    source: bytes
    language: str
    facts: TSFileFacts = field(default_factory=TSFileFacts)

    def visit_children(
        self,
        node: ASTNode,
        *,
        parent_index: int | None,
        impl_type: str | None,
        outer: _Outer | None = None,
    ) -> None:
        children = node.children
        for position, child in enumerate(children):
            self.visit(
                child,
                siblings=children,
                position=position,
                parent_index=parent_index,
                impl_type=impl_type,
                outer=outer,
            )

    def visit(
        self,
        node: ASTNode,
        *,
        siblings: tuple[ASTNode, ...],
        position: int,
        parent_index: int | None,
        impl_type: str | None,
        outer: _Outer | None = None,
    ) -> None:
        language = self.language
        if node.type in _IMPORT_NODE_TYPES.get(language, frozenset()):
            self.facts.imports.append(
                TSImport(text=self._text(node).strip(), start_line=_start_line(node), end_line=_end_line(node))
            )
            return
        if node.type in _CLASS_NODE_TYPES.get(language, frozenset()):
            index = self._add_class(
                node, siblings=siblings, position=position, parent_index=parent_index, outer=outer
            )
            self.visit_children(node, parent_index=index, impl_type=None)
            return
        if node.type in _FUNCTION_NODE_TYPES.get(language, frozenset()):
            index = self._add_function(
                node,
                siblings=siblings,
                position=position,
                parent_index=parent_index,
                impl_type=impl_type,
                outer=outer,
            )
            self.visit_children(node, parent_index=index, impl_type=None)
            return
        if node.type in _BOUND_FUNCTION_TYPES and language in {"javascript", "typescript"}:
            index = self._add_bound_function(
                node, siblings=siblings, position=position, parent_index=parent_index, outer=outer
            )
            if index is not None:
                self.visit_children(node, parent_index=index, impl_type=None)
                return
        if node.type in _IMPL_TYPES:
            self._record_impl(node)
            implemented = _bare_name(self._field_text(node, "type") or "")
            self.visit_children(node, parent_index=parent_index, impl_type=implemented or None)
            return
        call_name = self._call_name(node)
        if call_name:
            self.facts.calls.append(TSCall(name=call_name, line=_start_line(node), declaration_index=parent_index))
        if node.type in _WRAPPER_TYPES and outer is None:
            outer = (siblings, position, node)
        self.visit_children(node, parent_index=parent_index, impl_type=impl_type, outer=outer)

    # -- declarations ----------------------------------------------------

    def _add_class(
        self,
        node: ASTNode,
        *,
        siblings: tuple[ASTNode, ...],
        position: int,
        parent_index: int | None,
        outer: _Outer | None = None,
    ) -> int:
        parent_class, interfaces = self._heritage(node)
        return self._append(
            TSDeclaration(
                kind="class",
                name=self._field_text(node, "name") or "",
                start_line=_start_line(node),
                end_line=_end_line(node),
                parent_index=parent_index,
                parent_class=parent_class,
                interfaces=interfaces,
                docstring=self._docstring(siblings, position, node, outer),
            )
        )

    def _add_function(
        self,
        node: ASTNode,
        *,
        siblings: tuple[ASTNode, ...],
        position: int,
        parent_index: int | None,
        impl_type: str | None,
        outer: _Outer | None = None,
    ) -> int:
        owning_type = impl_type or self._receiver_type(node)
        owner = "class" if (parent_index is not None or owning_type) else "module"
        return self._append(
            TSDeclaration(
                kind="function",
                name=self._field_text(node, "name") or self._method_name(node) or "",
                start_line=_start_line(node),
                end_line=_end_line(node),
                parent_index=parent_index,
                parameters=self._parameters(node),
                return_type=self._return_type(node),
                owner=owner,
                docstring=self._docstring(siblings, position, node, outer),
                impl_type=None if parent_index is not None else owning_type,
            )
        )

    def _receiver_type(self, node: ASTNode) -> str | None:
        """Type a Go method hangs off: `func (s *Server) Handle()` -> Server."""
        receiver = self._field_text(node, "receiver")
        if not receiver:
            return None
        match = _RECEIVER_PATTERN.search(receiver)
        return _bare_name(match.group(1)) if match else None

    def _add_bound_function(
        self,
        node: ASTNode,
        *,
        siblings: tuple[ASTNode, ...],
        position: int,
        parent_index: int | None,
        outer: _Outer | None = None,
    ) -> int | None:
        value = node.fields.get("value")
        if value is None or value.type not in _FUNCTION_VALUE_TYPES:
            return None
        name = self._field_text(node, "name") or self._field_text(node, "property") or ""
        if not name:
            return None
        return self._append(
            TSDeclaration(
                kind="function",
                name=name,
                start_line=_start_line(node),
                end_line=_end_line(value),
                parent_index=parent_index,
                parameters=self._parameters(value),
                return_type=self._return_type(value),
                owner="class" if parent_index is not None else "module",
                docstring=self._docstring(siblings, position, node, outer),
            )
        )

    def _append(self, declaration: TSDeclaration) -> int:
        self.facts.declarations.append(declaration)
        return len(self.facts.declarations) - 1

    def _record_impl(self, node: ASTNode) -> None:
        type_name = self._field_text(node, "type")
        trait_name = self._field_text(node, "trait")
        if not type_name or not trait_name:
            return
        self.facts.inheritance.append(
            TSInheritance(
                type_name=_bare_name(type_name),
                parent_name=_bare_name(trait_name),
                start_line=_start_line(node),
                end_line=_end_line(node),
            )
        )

    # -- signature pieces ------------------------------------------------

    def _heritage(self, node: ASTNode) -> tuple[str | None, tuple[str, ...]]:
        superclass = self._field_text(node, "superclass") or ""
        interfaces_text = self._field_text(node, "interfaces")
        heritage_parts = [
            self._text(child)
            for child in node.children
            if child.type in {"class_heritage", "extends_clause", "super_interfaces", "extends_interfaces"}
        ]
        combined = " ".join(part for part in [superclass, *heritage_parts] if part).strip()
        parent_match = _EXTENDS_PATTERN.search(combined) if combined else None
        parent_class = parent_match.group(1) if parent_match else None
        interfaces: list[str] = []
        interfaces_source = interfaces_text or combined
        if interfaces_source:
            match = _IMPLEMENTS_PATTERN.search(interfaces_source)
            if match:
                interfaces = [_bare_name(part) for part in match.group(1).split(",")]
        return parent_class, tuple(name for name in interfaces if name)

    def _parameters(self, node: ASTNode) -> tuple[Parameter, ...]:
        params_node = node.fields.get("parameters")
        if params_node is None:
            params_node = next((child for child in node.children if child.type in _PARAMETER_LIST_TYPES), None)
        if params_node is None:
            return ()
        parameters: list[Parameter] = []
        for child in params_node.children:
            if not child.named or "comment" in child.type:
                continue
            parameters.extend(self._parameter(child))
        return tuple(parameters)

    def _parameter(self, node: ASTNode) -> list[Parameter]:
        node_type = node.type
        if node_type == "self_parameter":
            return [Parameter(name=_clean_name(self._text(node)) or "self", type=None, defaultValue=None)]
        if node_type in {"required_parameter", "optional_parameter"}:
            return [
                Parameter(
                    name=_clean_name(self._field_text(node, "pattern") or self._text(node)),
                    type=_clean_type(self._field_text(node, "type")),
                    defaultValue=_clean_type(self._field_text(node, "value")),
                )
            ]
        if node_type == "assignment_pattern":
            return [
                Parameter(
                    name=_clean_name(self._field_text(node, "left") or ""),
                    type=None,
                    defaultValue=_clean_type(self._field_text(node, "right")),
                )
            ]
        if node_type in {"formal_parameter", "receiver_parameter", "spread_parameter"}:
            return [
                Parameter(
                    name=_clean_name(self._field_text(node, "name") or self._text(node)),
                    type=_clean_type(self._field_text(node, "type")),
                    defaultValue=None,
                )
            ]
        if node_type in {"parameter_declaration", "variadic_parameter_declaration"}:
            type_text = _clean_type(self._field_text(node, "type"))
            names = [self._text(child) for child in node.children if child.type == "identifier"]
            if not names:
                return [Parameter(name=_clean_name(self._text(node)), type=type_text, defaultValue=None)]
            return [Parameter(name=_clean_name(name), type=type_text, defaultValue=None) for name in names]
        if node_type == "parameter":
            return [
                Parameter(
                    name=_clean_name(self._field_text(node, "pattern") or self._text(node)),
                    type=_clean_type(self._field_text(node, "type")),
                    defaultValue=None,
                )
            ]
        return [Parameter(name=_clean_name(self._text(node)), type=None, defaultValue=None)]

    def _return_type(self, node: ASTNode) -> str | None:
        for field_name in ("return_type", "result", "type"):
            value = node.fields.get(field_name)
            if value is not None:
                return _clean_type(self._text(value))
        return None

    def _member_name(self, node: ASTNode) -> str | None:
        for field_name in ("property", "field", "name"):
            value = self._field_text(node, field_name)
            if value:
                return value
        return None

    def _method_name(self, node: ASTNode) -> str | None:
        for child in node.children:
            if child.type in {"property_identifier", "identifier", "field_identifier", "type_identifier"}:
                return self._text(child)
        return None

    def _call_name(self, node: ASTNode) -> str | None:
        node_type = node.type
        if node_type == "call_expression":
            callee = node.fields.get("function")
            if callee is None:
                return None
            # `a.b().c()` - the callee text of the outer call contains the
            # inner call, so fall back to the member name alone.
            return _bare_call(self._text(callee)) or _bare_call(self._member_name(callee))
        if node_type == "method_invocation":
            name = self._field_text(node, "name")
            obj = self._field_text(node, "object")
            if name and obj and "\n" not in obj and len(obj) <= 60:
                return _bare_call(f"{obj}.{name}")
            return _bare_call(name)
        if node_type == "macro_invocation":
            macro = self._field_text(node, "macro")
            return _bare_call(f"{macro}!") if macro else None
        if node_type in {"object_creation_expression", "new_expression"}:
            return _bare_call(self._field_text(node, "type") or self._field_text(node, "constructor"))
        return None

    # -- text helpers ----------------------------------------------------

    def _docstring(
        self,
        siblings: tuple[ASTNode, ...],
        position: int,
        node: ASTNode,
        outer: _Outer | None = None,
    ) -> str:
        text = self._preceding_comments(siblings, position, node)
        if text or outer is None:
            return text
        return self._preceding_comments(*outer)

    def _preceding_comments(self, siblings: tuple[ASTNode, ...], position: int, node: ASTNode) -> str:
        collected: list[str] = []
        expected_row = node.start_point.row
        index = position - 1
        while index >= 0:
            sibling = siblings[index]
            if "comment" not in sibling.type:
                break
            if sibling.end_point.row < expected_row - 1:
                break
            collected.append(self._text(sibling))
            expected_row = sibling.start_point.row
            index -= 1
        collected.reverse()
        return _clean_comment_block(collected)

    def _field_text(self, node: ASTNode, name: str) -> str | None:
        value = node.fields.get(name)
        if value is None:
            return None
        text = self._text(value).strip()
        return text or None

    def _text(self, node: ASTNode) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _module_docstring(root: ASTNode, source: bytes) -> str:
    collected: list[str] = []
    expected_row = 0
    for child in root.children:
        if "comment" not in child.type:
            break
        if child.start_point.row > expected_row:
            break
        collected.append(source[child.start_byte : child.end_byte].decode("utf-8", errors="replace"))
        expected_row = child.end_point.row + 1
    return _clean_comment_block(collected)


def _clean_comment_block(comments: Iterable[str]) -> str:
    lines: list[str] = []
    for comment in comments:
        for raw in comment.splitlines():
            line = raw.strip()
            if line.endswith("*/"):
                line = line[:-2].strip()
            if line.startswith("/**"):
                line = line[3:]
            elif line.startswith("/*"):
                line = line[2:]
            if line.startswith("///"):
                line = line[3:]
            elif line.startswith("//"):
                line = line[2:]
            if line.startswith("*"):
                line = line[1:]
            if line.startswith("!"):
                line = line[1:]
            line = line.strip()
            if line:
                lines.append(line)
    return "\n".join(lines)


def _clean_name(value: str) -> str:
    cleaned = value.strip().lstrip("*&").strip()
    if cleaned.startswith("mut "):
        cleaned = cleaned[4:].strip()
    return cleaned


def _clean_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    for prefix in (":", "->", "="):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned.strip(",").strip() or None


def _bare_name(value: str) -> str:
    return value.strip().split("<", 1)[0].strip()


def _bare_call(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split())
    if not cleaned or "(" in cleaned or len(cleaned) > 120:
        return None
    return cleaned


def _start_line(node: ASTNode) -> int:
    return node.start_point.row + 1


def _end_line(node: ASTNode) -> int:
    return max(node.start_point.row + 1, node.end_point.row + 1)
