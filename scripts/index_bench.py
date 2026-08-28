"""Time a full indexing run, stage by stage.

A total alone cannot tell you whether summarization or embedding moved, and
those two are the only stages large enough to care about. This drives
`cli.index_command.run_index` - exactly what `codepedia index` calls, minus
the blocking web server it starts afterwards - and times each stage from the
banner the pipeline itself prints when that stage begins.

Timing from the *start* banners, rather than from any explicit duration line,
is deliberate: those banners have been printed since 019, so the same script
measures an older revision (checked out in a `git worktree`) and the current
one without the older revision needing to be modified to be measurable.

    python scripts/index_bench.py <repo> [--label name] [--fresh] [--json out.json]

`--fresh` deletes the repository's existing index first, which is what makes a
run comparable to a cold baseline. Omit it to measure a re-index, which is
where the embedding cache shows up.

Runs against whatever provider chain `~/.codepedia/config.json` configures, so
it makes real API calls and spends real quota.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cli import paths  # noqa: E402
from cli.config import load_config  # noqa: E402
from cli.index_command import Stage, run_index  # noqa: E402

_STAGE_LABELS = {stage.value for stage in Stage}


class _TimestampingStream:
    """Passes output through untouched while recording when each line arrived.

    `typer.echo` writes to whatever `sys.stdout` is at call time, so wrapping
    it captures the pipeline's own progress banners without the pipeline
    needing to know it is being measured.
    """

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped
        self._buffer = ""
        self.events: list[tuple[float, str]] = []

    def write(self, text: str) -> int:
        self._wrapped.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition("\n")
            self.events.append((time.perf_counter(), line))
        return len(text)

    def flush(self) -> None:
        self._wrapped.flush()

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


@dataclass
class BenchReport:
    label: str
    repository: str
    fresh: bool
    totalSeconds: float = 0.0
    failed: str = ""
    stageSeconds: dict[str, float] = field(default_factory=dict)
    embeddingsReused: int = 0
    embeddingsComputed: int = 0
    backoffWaits: int = 0

    def render(self) -> str:
        lines = [
            f"{self.label} - {self.repository} ({'cold' if self.fresh else 're-index'})",
            f"  total {self.totalSeconds:.1f}s" + (f"  FAILED: {self.failed}" if self.failed else ""),
        ]
        for stage, seconds in self.stageSeconds.items():
            share = (seconds / self.totalSeconds * 100) if self.totalSeconds else 0.0
            lines.append(f"    {stage:<36} {seconds:>8.1f}s  ({share:4.1f}%)")
        if self.embeddingsReused or self.embeddingsComputed:
            total_chunks = self.embeddingsReused + self.embeddingsComputed
            share = (self.embeddingsReused / total_chunks * 100) if total_chunks else 0.0
            lines.append(
                f"  embeddings: {self.embeddingsComputed} computed, "
                f"{self.embeddingsReused} reused ({share:.0f}% of {total_chunks})"
            )
        if self.backoffWaits:
            lines.append(f"  rate-limit waits: {self.backoffWaits}")
        return "\n".join(lines)


def _stage_durations(events: list[tuple[float, str]], finished_at: float) -> dict[str, float]:
    """Each stage lasts until the next stage announces itself."""
    marks = [(moment, line) for moment, line in events if line in _STAGE_LABELS]
    durations: dict[str, float] = {}
    for index, (moment, label) in enumerate(marks):
        ends_at = marks[index + 1][0] if index + 1 < len(marks) else finished_at
        durations[label] = ends_at - moment
    return durations


def _count_extras(report: BenchReport, events: list[tuple[float, str]]) -> None:
    """Read the two counters only the post-032 pipeline prints.

    Absent on an older revision, which simply leaves them at zero rather than
    making the script revision-specific.
    """
    for _, line in events:
        stripped = line.strip()
        if stripped.startswith("reused ") and "from cache, computed " in stripped:
            reused, _, rest = stripped[len("reused ") :].partition(" embedding(s) from cache, computed ")
            report.embeddingsReused = int(reused)
            report.embeddingsComputed = int(rest.strip())
        elif stripped.startswith("rate limited by "):
            report.backoffWaits += 1


def run_bench(
    repository: Path,
    *,
    label: str,
    fresh: bool,
    embedding_chain: tuple[str, ...] | None = None,
    summary_chain: tuple[str, ...] | None = None,
) -> BenchReport:
    """Chain overrides are applied to the loaded configuration in memory only.

    The user's `config.json` is never rewritten - a benchmark that edits the
    configuration it is measuring is a benchmark that can leave the machine in
    a state its owner did not ask for.
    """
    report = BenchReport(label=label, repository=str(repository), fresh=fresh)
    if fresh:
        state_dir = paths.repo_state_dir(repository)
        if state_dir.exists():
            shutil.rmtree(state_dir, ignore_errors=True)

    config = load_config()
    overrides: dict[str, object] = {}
    if embedding_chain is not None:
        overrides["embeddingChain"] = tuple(embedding_chain)
    if summary_chain is not None:
        overrides["summaryChain"] = tuple(summary_chain)
    if overrides:
        config = replace(config, **overrides)
        print(f"[bench] chain overrides: {overrides}")

    stream = _TimestampingStream(sys.stdout)
    original_stdout = sys.stdout
    sys.stdout = stream  # type: ignore[assignment]
    started = time.perf_counter()
    result = None
    try:
        result = run_index(repository, config=config)
    except Exception as exc:  # noqa: BLE001 - a failed run is still a measurement
        report.failed = f"{type(exc).__name__}: {exc}"
    finally:
        finished = time.perf_counter()
        sys.stdout = original_stdout
        if result is not None:
            result.vectorIndex.close()

    report.totalSeconds = finished - started
    report.stageSeconds = _stage_durations(stream.events, finished)
    _count_extras(report, stream.events)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository", type=Path, help="repository to index")
    parser.add_argument("--label", default="run", help="name for this run in the report")
    parser.add_argument("--fresh", action="store_true", help="delete any existing index first")
    parser.add_argument("--json", type=Path, default=None, help="also write the report as JSON")
    parser.add_argument(
        "--embedding-chain",
        default=None,
        help="comma-separated chain overriding config.json for this run only",
    )
    parser.add_argument(
        "--summary-chain",
        default=None,
        help="comma-separated chain overriding config.json for this run only",
    )
    args = parser.parse_args(argv)

    report = run_bench(
        args.repository.expanduser().resolve(),
        label=args.label,
        fresh=args.fresh,
        embedding_chain=tuple(args.embedding_chain.split(",")) if args.embedding_chain else None,
        summary_chain=tuple(args.summary_chain.split(",")) if args.summary_chain else None,
    )
    print()
    print(report.render())
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
