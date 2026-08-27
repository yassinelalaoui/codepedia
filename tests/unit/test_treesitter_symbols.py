"""The tree-sitter extraction path for the brace languages.

These assert the facts the line-oriented regex scanner cannot reach:
multi-line signatures, arrow functions bound to a const, methods declared
outside their type's body, and separated `extends`/`implements` lists.
"""

from pathlib import Path

import pytest

from parser_engine import SourceFile, extract_symbols
from parser_engine.treesitter_runtime import get_runtime

pytestmark = pytest.mark.skipif(
    not get_runtime().is_available("typescript"),
    reason="tree-sitter grammars are not installed",
)


TYPESCRIPT_SAMPLE = '''/**
 * Renders the table of contents.
 */
import { useEffect, useState } from "react";

export interface TocProps {
  headings: string[];
}

export class TocHighlighter extends BaseWidget implements Disposable {
  /** Start observing. */
  public observe(
    headings: string[],
    threshold: number = 0.5,
  ): void {
    this.observer = new IntersectionObserver(this.handle, { threshold });
  }

  dispose(): void {
    this.observer.disconnect();
  }
}

export const useToc = (headings: string[]): string | null => {
  return headings[0] ?? null;
};
'''

GO_SAMPLE = '''// Package svc serves things.
package svc

import (
\t"context"
\t"fmt"
)

// Server handles requests.
type Server struct {
\tname string
}

// Handle runs the request.
func (s *Server) Handle(
\tctx context.Context,
\tid string,
) (string, error) {
\tfmt.Println(s.name)
\treturn id, nil
}
'''

RUST_SAMPLE = '''//! Crate docs.
use std::collections::HashMap;

/// A cache.
pub struct Cache {
    entries: HashMap<String, String>,
}

pub trait Store {
    fn get(&self, key: &str) -> Option<String>;
}

impl Store for Cache {
    /// Look up a key.
    fn get(&self, key: &str) -> Option<String> {
        self.entries.get(key).cloned()
    }
}
'''

JAVA_SAMPLE = '''package app;

import java.util.List;

/** Entry point. */
public class Main extends Base implements Runnable, Closeable {
    public void run() {
        System.out.println(items.size());
    }
}
'''


def _inventory(name: str, language: str, text: str):
    return extract_symbols(SourceFile(path=Path(name), language=language, content=text))


def test_typescript_multiline_signatures_and_arrow_functions():
    inventory = _inventory("Toc.ts", "typescript", TYPESCRIPT_SAMPLE)

    functions = {item.name: item for item in inventory.functions}
    assert set(functions) == {"observe", "dispose", "useToc"}

    observe = functions["observe"]
    assert [(param.name, param.type) for param in observe.parameters] == [
        ("headings", "string[]"),
        ("threshold", "number"),
    ]
    assert observe.parameters[1].defaultValue == "0.5"
    assert observe.returnType == "void"
    assert observe.docstring == "Start observing."
    assert observe.owner == "class"

    # An arrow function bound to an exported const is a module-level function.
    assert functions["useToc"].owner == "module"
    assert functions["useToc"].returnType == "string | null"

    classes = {item.name: item for item in inventory.classes}
    assert set(classes) == {"TocProps", "TocHighlighter"}
    assert classes["TocHighlighter"].parentClass == "BaseWidget"
    assert [method.name for method in classes["TocHighlighter"].methods] == ["observe", "dispose"]
    assert inventory.module.docstring == "Renders the table of contents."


def test_typescript_separates_extends_from_implements():
    inventory = _inventory("Toc.ts", "typescript", TYPESCRIPT_SAMPLE)

    parents = {relation.parentClassName for relation in inventory.inheritanceRelations}
    assert parents == {"BaseWidget", "Disposable"}


def test_go_methods_hang_off_their_receiver_type():
    inventory = _inventory("svc.go", "go", GO_SAMPLE)

    server = next(item for item in inventory.classes if item.name == "Server")
    assert server.docstring == "Server handles requests."
    assert [method.name for method in server.methods] == ["Handle"]

    handle = next(item for item in inventory.functions if item.name == "Handle")
    assert [param.name for param in handle.parameters] == ["ctx", "id"]
    assert handle.owner == "class"
    assert inventory.module.docstring == "Package svc serves things."
    assert any("context" in record.text for record in inventory.imports)


def test_rust_impl_methods_are_attached_to_their_type():
    inventory = _inventory("lib.rs", "rust", RUST_SAMPLE)

    cache = next(item for item in inventory.classes if item.name == "Cache")
    assert [method.name for method in cache.methods] == ["get"]
    assert cache.docstring == "A cache."
    assert inventory.module.docstring == "Crate docs."

    assert any(
        relation.parentClassName == "Store" and relation.subclassSymbolId == cache.id
        for relation in inventory.inheritanceRelations
    )


def test_java_records_superclass_and_every_interface():
    inventory = _inventory("Main.java", "java", JAVA_SAMPLE)

    main = next(item for item in inventory.classes if item.name == "Main")
    assert main.parentClass == "Base"
    assert main.docstring == "Entry point."
    assert {relation.parentClassName for relation in inventory.inheritanceRelations} == {
        "Base",
        "Runnable",
        "Closeable",
    }
    assert {call.calleeSymbolIdOrName for call in inventory.callRelations} == {
        "System.out.println",
        "items.size",
    }


def test_symbol_ids_stay_unique_across_a_file():
    inventory = _inventory("lib.rs", "rust", RUST_SAMPLE)

    ids = [item.id for item in inventory.classes] + [item.id for item in inventory.functions]
    assert len(ids) == len(set(ids))


def test_broken_source_still_yields_symbols():
    """tree-sitter recovers from the missing braces instead of giving up."""
    broken = "class Widget extends Base {\n  render() {\n    return 1;\n"

    inventory = _inventory("broken.ts", "typescript", broken)

    assert [item.name for item in inventory.classes] == ["Widget"]


def test_missing_grammar_falls_back_to_the_regex_scanner(monkeypatch):
    from parser_engine import parser_registry

    def unavailable(language: str):
        raise RuntimeError("no grammar for " + language)

    monkeypatch.setattr(parser_registry, "get_parser", unavailable)

    inventory = _inventory("Toc.ts", "typescript", TYPESCRIPT_SAMPLE)

    # The regex scanner sees the single-line declarations only, which is
    # exactly why it is a fallback and no longer the default path.
    assert [item.name for item in inventory.classes] == ["TocHighlighter"]
    assert [item.name for item in inventory.functions] == ["dispose"]
