"""Compare the tree-sitter and regex symbol inventories over a repository.

The regex scanner used to be the only extraction path for the brace
languages; tree-sitter is now the default and the regex scanner is the
fallback. This script re-extracts a whole repository with both and reports
what the switch adds, per language.

    python scripts/inventory_report.py <repo> [--json report.json] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from parser_engine import SourceFile, extract_symbols  # noqa: E402
from parser_engine.extractor import (  # noqa: E402
    BRACE_LANGUAGES,
    _extract_brace_inventory,
    _normalize_language,
)
from repo_scanner.models import RepositoryScanRequest  # noqa: E402
from repo_scanner.scanner import scan_repository  # noqa: E402

COUNTED = ("classes", "functions", "imports", "callRelations", "inheritanceRelations")
# The regex scanner matches `if (...) {` as a declaration named "if"; counting
# those separately keeps the comparison honest about what each path really found.
KEYWORD_NAMES = frozenset(
    {"if", "else", "for", "while", "do", "switch", "case", "catch", "try", "return", "new", "func", "fn", "class"}
)


@dataclass
class Totals:
    files: int = 0
    counts: dict[str, int] = field(default_factory=lambda: {key: 0 for key in COUNTED})
    documented: int = 0
    typed_parameters: int = 0
    parameters: int = 0
    keyword_named: int = 0

    def add(self, inventory) -> None:
        self.files += 1
        for key in COUNTED:
            self.counts[key] += len(getattr(inventory, key))
        for symbol in (*inventory.classes, *inventory.functions):
            if symbol.docstring:
                self.documented += 1
            if symbol.name in KEYWORD_NAMES:
                self.keyword_named += 1
        for function in inventory.functions:
            for parameter in function.parameters:
                self.parameters += 1
                if parameter.type:
                    self.typed_parameters += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "files": self.files,
            **self.counts,
            "documentedSymbols": self.documented,
            "parameters": self.parameters,
            "typedParameters": self.typed_parameters,
            "keywordNamedSymbols": self.keyword_named,
            "realSymbols": self.counts["classes"] + self.counts["functions"] - self.keyword_named,
        }


def build_report(repository: Path, limit: int | None = None) -> dict[str, dict[str, dict[str, int]]]:
    scan = scan_repository(RepositoryScanRequest(root_path=repository))
    report: dict[str, dict[str, Totals]] = {}
    processed = 0
    for entry in scan.entries:
        language = _normalize_language(entry.language)
        if language not in BRACE_LANGUAGES:
            continue
        path = repository / entry.relative_path
        source = SourceFile(path=path, language=language)
        try:
            text = source.read_text()
        except OSError:
            continue
        per_language = report.setdefault(language, {"treesitter": Totals(), "regex": Totals()})
        per_language["treesitter"].add(extract_symbols(source))
        per_language["regex"].add(_extract_brace_inventory(source_file=source, text=text, language=language))
        processed += 1
        if limit is not None and processed >= limit:
            break
    return {
        language: {engine: totals.to_dict() for engine, totals in engines.items()}
        for language, engines in report.items()
    }


def print_report(report: dict[str, dict[str, dict[str, int]]]) -> None:
    metrics = (
        "files",
        *COUNTED,
        "documentedSymbols",
        "parameters",
        "typedParameters",
        "keywordNamedSymbols",
        "realSymbols",
    )
    for language in sorted(report):
        new = report[language]["treesitter"]
        old = report[language]["regex"]
        print(f"\n{language}  ({new['files']} files)")
        print(f"  {'metric':<22}{'regex':>10}{'tree-sitter':>14}{'delta':>10}")
        for metric in metrics:
            if metric == "files":
                continue
            before, after = old[metric], new[metric]
            delta = after - before
            print(f"  {metric:<22}{before:>10}{after:>14}{delta:>+10}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--json", type=Path, default=None, help="write the raw counts to this file")
    parser.add_argument("--limit", type=int, default=None, help="stop after N source files")
    args = parser.parse_args(argv)

    repository = args.repository.expanduser().resolve()
    report = build_report(repository, limit=args.limit)
    if not report:
        print(f"no javascript/typescript/java/go/rust files found under {repository}")
        return 1
    print_report(report)
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
