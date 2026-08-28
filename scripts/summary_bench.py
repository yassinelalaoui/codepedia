"""Time the summarization stage alone, at several pool sizes.

`index_bench.py` measures a whole pipeline run, which is the honest end-to-end
number but pays for the embedding stage too - prohibitive on a machine whose
only reachable embedding provider is a local model at several seconds a call.
This isolates `SUMMARIZING`, the stage that dominates indexing, so it can be
measured over a corpus large enough to mean something.

`--workers 1` is the sequential baseline, not an approximation of it: a pool
of one runs its tasks in submission order, and the pool's own overhead is
microseconds against a call that takes about a second.

    python scripts/summary_bench.py <path> [--workers 1,4,8] [--json out.json]

Every pass re-summarizes the whole corpus against the configured provider, so
N passes cost N times the API calls.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cli.config import load_config  # noqa: E402
from dependency_graph import DependencyGraph  # noqa: E402
from parser_engine import SourceFile, extract_symbols  # noqa: E402
from provider_routing import build_stage_executor  # noqa: E402
from repo_scanner.scanner import scan_repository  # noqa: E402
from repository_metadata import CodeSummaryPipeline, RepositoryMetadataStore, compute_content_hash  # noqa: E402


@dataclass
class Pass:
    workers: int
    seconds: float
    symbols: int
    failed: str = ""


@dataclass
class SummaryBenchReport:
    target: str
    chain: list[str] = field(default_factory=list)
    passes: list[Pass] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"summarization stage - {self.target}", f"  chain: {' -> '.join(self.chain)}"]
        sequential = next((item for item in self.passes if item.workers == 1 and not item.failed), None)
        for item in self.passes:
            if item.failed:
                lines.append(f"    workers={item.workers:<3} FAILED: {item.failed}")
                continue
            per_symbol = item.seconds / item.symbols if item.symbols else 0.0
            speedup = f"  {sequential.seconds / item.seconds:.2f}x" if sequential and item.seconds else ""
            lines.append(
                f"    workers={item.workers:<3} {item.seconds:>7.1f}s for {item.symbols} symbols "
                f"({per_symbol:.2f}s/symbol){speedup}"
            )
        return "\n".join(lines)


def _prepare(target: Path, state_dir: Path):
    """Parse and persist the corpus once, so every pass starts from the same
    stored state and measures only the summarization calls."""
    store = RepositoryMetadataStore(state_dir / "repository-metadata.sqlite")
    scan_result = scan_repository(target)
    languages = tuple(sorted({entry.language for entry in scan_result.entries}))
    store.ensure_repository(target, detected_languages=languages)
    inventories = []
    for entry in scan_result.entries:
        absolute_path = target / entry.relative_path
        source_file = SourceFile(path=absolute_path, language=entry.language)
        inventory = extract_symbols(source_file)
        store.store_inventory(
            repository_root=target,
            source_file=source_file,
            inventory=inventory,
            content_hash=compute_content_hash(absolute_path),
        )
        inventories.append(inventory)
    graph = DependencyGraph.build_from_inventories(inventories, sourceFile=str(target))
    return store, graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path)
    parser.add_argument("--workers", default="1,4", help="comma-separated pool sizes to compare")
    parser.add_argument("--summary-chain", default=None, help="comma-separated chain override for this run only")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    target = args.target.expanduser().resolve()
    config = load_config()
    if args.summary_chain:
        from dataclasses import replace

        config = replace(config, summaryChain=tuple(args.summary_chain.split(",")))

    report = SummaryBenchReport(target=str(target), chain=list(config.summaryChain))
    state_dir = Path(tempfile.mkdtemp(prefix="summary-bench-"))
    try:
        for workers in [int(value) for value in args.workers.split(",")]:
            # A fresh store per pass: a summary already stored would otherwise
            # let a later pass measure different work than the first one did.
            pass_dir = state_dir / f"workers-{workers}"
            pass_dir.mkdir(parents=True, exist_ok=True)
            store, graph = _prepare(target, pass_dir)
            executor = build_stage_executor("summary", config)
            pipeline = CodeSummaryPipeline(
                metadataStore=store, dependencyGraph=graph, llmEngine=executor, maxWorkers=workers
            )
            started = time.perf_counter()
            try:
                results = pipeline.summarizeRepository(target, incremental=False)
                elapsed = time.perf_counter() - started
                report.passes.append(Pass(workers=workers, seconds=elapsed, symbols=len(results)))
                print(f"  workers={workers}: {elapsed:.1f}s for {len(results)} symbols")
            except Exception as exc:  # noqa: BLE001 - a failed pass is still a result
                report.passes.append(
                    Pass(
                        workers=workers,
                        seconds=time.perf_counter() - started,
                        symbols=0,
                        failed=f"{type(exc).__name__}: {exc}",
                    )
                )
                print(f"  workers={workers}: FAILED {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(state_dir, ignore_errors=True)

    print()
    print(report.render())
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
