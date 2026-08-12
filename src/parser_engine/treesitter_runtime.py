from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import import_module
from typing import Any

LANGUAGE_MODULES = {
    "python": ("tree_sitter_python", ("language",)),
    "javascript": ("tree_sitter_javascript", ("language",)),
    "typescript": ("tree_sitter_typescript", ("language_typescript", "language")),
    "java": ("tree_sitter_java", ("language",)),
    "go": ("tree_sitter_go", ("language",)),
    "rust": ("tree_sitter_rust", ("language",)),
}


@dataclass(slots=True)
class TreeSitterRuntime:
    _language_cache: dict[str, Any] = field(default_factory=dict)
    _parser_cache: dict[str, Any] = field(default_factory=dict)

    def is_available(self, language_key: str) -> bool:
        return self._load_language(language_key) is not None and self._load_parser_class() is not None

    def parse(self, language_key: str, content: str | bytes) -> Any:
        parser = self._load_parser(language_key)
        if parser is None:
            raise RuntimeError(f"Tree-sitter runtime unavailable for {language_key}")
        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        tree = parser.parse(payload)
        if tree is None:
            raise RuntimeError(f"Tree-sitter returned no tree for {language_key}")
        return tree

    def _load_parser_class(self) -> Any | None:
        try:
            from tree_sitter import Parser as TreeSitterParser  # type: ignore
        except Exception:
            return None
        return TreeSitterParser

    def _load_language(self, language_key: str) -> Any | None:
        key = normalize_language_key(language_key)
        if key in self._language_cache:
            return self._language_cache[key]
        module_info = LANGUAGE_MODULES.get(key)
        if module_info is None:
            return None
        module_name, function_names = module_info
        try:
            module = import_module(module_name)
        except Exception:
            return None
        language_value = None
        for function_name in function_names:
            factory = getattr(module, function_name, None)
            if callable(factory):
                try:
                    language_value = factory()
                    break
                except Exception:
                    continue
        if language_value is None:
            return None
        language_value = self._wrap_language(language_value)
        if language_value is None:
            return None
        self._language_cache[key] = language_value
        return language_value

    def _wrap_language(self, language_value: Any) -> Any | None:
        try:
            from tree_sitter import Language as TreeSitterLanguage  # type: ignore
        except Exception:
            return language_value
        if isinstance(language_value, TreeSitterLanguage):
            return language_value
        try:
            return TreeSitterLanguage(language_value)
        except Exception:
            return language_value

    def _load_parser(self, language_key: str) -> Any | None:
        key = normalize_language_key(language_key)
        if key in self._parser_cache:
            return self._parser_cache[key]
        parser_cls = self._load_parser_class()
        language = self._load_language(key)
        if parser_cls is None or language is None:
            return None
        try:
            parser = parser_cls()
            try:
                parser.language = language
            except Exception:
                parser = parser_cls(language)
        except Exception:
            return None
        self._parser_cache[key] = parser
        return parser


@lru_cache(maxsize=1)
def get_runtime() -> TreeSitterRuntime:
    return TreeSitterRuntime()


def normalize_language_key(language_key: str) -> str:
    value = language_key.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
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

