"""Launch and supervise the real CLI as a child process (research.md §1, §7, §8).

Three things here are load-bearing and easy to get wrong:

1. **The stdout reader thread must never stop.** A child server's watcher keeps
   printing for as long as it runs. An undrained pipe fills, the child blocks on
   its next write, and the server silently stops answering. That is why parsing
   is total (`progress_parse` never raises) and why every non-event line is
   forwarded rather than examined.

2. **Terminating a child does not run its cleanup.** `run_index` removes its
   staging directory in an `except Exception:` handler, which `TerminateProcess`
   does not trigger. So the hub deletes it afterwards, by the child's own pid -
   otherwise spec FR-012a's "discard its partial work" would be a claim rather
   than a fact, and cancelling would become a new source of the residue the
   history listing has to filter.

3. **Exit code is authoritative, events are only diagnosis.** A child killed
   before it can say anything still has to end the run (spec FR-021).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from cli import paths as cli_paths
from cli.progress_stream import ENV_VAR

from .progress_parse import ProgressEvent, is_event_line, parse_line

# How the startup line reads today (`chat_api/security.py:95-112`). Parsed as a
# fallback only - the child also emits a `server_ready` event - so that an older
# child still works and this hub does not depend on that sentence's wording.
_URL_MARKER = "available at "

TERMINATE_GRACE_SECONDS = 5.0


def free_port() -> int:
    """Ask the OS for a port nobody is using.

    Bind-then-release leaves a theoretical window before the child binds it. On
    a loopback interface with one user that is negligible, and spec FR-037
    already requires a failure to start another server be reported rather than
    silent - so the race degrades into a message, not a mystery.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def child_environment() -> dict[str, str]:
    """The child's environment, with the progress channel switched on.

    This is the *only* place the variable is set. Everything about spec FR-002
    rests on that: a person's own `codepedia index` never sees it.
    """
    environment = dict(os.environ)
    environment[ENV_VAR] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    # Unbuffered, so a line written by the child is a line the hub can read.
    # Without it the interpreter block-buffers into a pipe and progress arrives
    # in clumps regardless of the child's own flushing.
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


@dataclass
class ChildProcess:
    """A running `python -m cli ...`, with its output being drained."""

    kind: str
    repositoryPath: str
    process: subprocess.Popen
    onEvent: Callable[[ProgressEvent], None]
    onLine: Callable[[str], None]
    stateId: Optional[str] = None
    port: Optional[int] = None
    url: Optional[str] = None
    lines: list[str] = field(default_factory=list)
    _reader: Optional[threading.Thread] = None
    _urlReady: threading.Event = field(default_factory=threading.Event)

    @property
    def pid(self) -> int:
        return self.process.pid

    def start_reader(self) -> None:
        self._reader = threading.Thread(target=self._drain, name=f"cp-child-{self.pid}", daemon=True)
        self._reader.start()

    def _drain(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        try:
            for raw in stream:
                line = raw.rstrip("\r\n")
                if is_event_line(line):
                    event = parse_line(line)
                    if event is not None:
                        try:
                            self.onEvent(event)
                        except Exception:  # noqa: BLE001 - see module docstring
                            # A consumer bug must not stop the drain and hang
                            # the child. Losing one event costs a redraw.
                            pass
                    if event is not None and event.type == "server_ready":
                        self.url = event.get("url")
                        self._urlReady.set()
                    continue

                # Not an event: it belongs to the terminal, verbatim
                # (spec FR-016).
                self.onLine(line)
                # Bounded: a long-running server prints indefinitely, and the
                # tail is all a failure message needs.
                self.lines.append(line)
                del self.lines[:-200]
                if self.url is None and _URL_MARKER in line:
                    self.url = line.split(_URL_MARKER, 1)[1].strip()
                    self._urlReady.set()
        except (OSError, ValueError):
            # The pipe closed under us; the child is gone and its exit code is
            # what matters now.
            pass
        finally:
            self._urlReady.set()

    def wait_for_url(self, timeout: float) -> Optional[str]:
        self._urlReady.wait(timeout)
        return self.url

    def is_running(self) -> bool:
        return self.process.poll() is None

    def terminate(self) -> None:
        """Stop the child, then make sure it is actually stopped."""
        if self.process.poll() is not None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        except OSError:
            pass

    def tail(self, count: int = 12) -> str:
        return "\n".join(self.lines[-count:])


def launch(
    *,
    kind: str,
    args: list[str],
    repository_path: str,
    on_event: Callable[[ProgressEvent], None],
    on_line: Callable[[str], None],
    cwd: Optional[Path] = None,
) -> ChildProcess:
    """Start `python -m cli <args>` with its stdout piped and drained."""
    process = subprocess.Popen(
        [sys.executable, "-m", "cli", *args],
        stdout=subprocess.PIPE,
        # Folded into stdout deliberately: the hub forwards both to its own
        # terminal, and interleaving them preserves the order a person would
        # have seen had they run the command themselves.
        stderr=subprocess.STDOUT,
        env=child_environment(),
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        # A repository path or a summary can carry anything; a decode error must
        # not kill the reader and with it the child
        # (contracts/run-progress-stream.md, reader obligation 5).
        errors="replace",
        bufsize=1,
    )
    child = ChildProcess(
        kind=kind,
        repositoryPath=repository_path,
        process=process,
        onEvent=on_event,
        onLine=on_line,
    )
    child.start_reader()
    return child


def staging_dir_for(repository_path: str, pid: int) -> Path:
    """Where `run_index` in process `pid` builds its output.

    Mirrors `index_command.py:234` exactly - `<state_id>.staging-<pid>` beside
    the final state directory.
    """
    state_dir = cli_paths.repo_state_dir(Path(repository_path))
    return state_dir.parent / f"{state_dir.name}.staging-{pid}"


def discard_staging(repository_path: str, pid: int) -> bool:
    """Remove the staging directory a killed child left behind (spec FR-012a).

    Only ever the directory belonging to *this* pid. Residue from other runs -
    including the seven already sitting in `~/.codepedia/repos/` on this machine
    - is left alone: it may belong to a live process, and cleaning it up is
    explicitly out of scope for this feature.
    """
    staging = staging_dir_for(repository_path, pid)
    if not staging.exists():
        return False
    shutil.rmtree(staging, ignore_errors=True)
    return not staging.exists()


def classify_failure(child: ChildProcess) -> dict[str, Any]:
    """Say what went wrong in the terms the person needs (data-model.md §4).

    The distinction between "your stored analysis is unusable" and "no provider
    is available" matters more than it looks. `run_serve` checks all three
    provider chains before doing anything (`serve_command.py:36`), so on a
    machine with an unreachable embedding chain every Open fails even though the
    wiki is complete on disk (research.md §11). Reporting that as a broken
    analysis would be a false diagnosis, and would send someone off to re-run an
    index that was never the problem - hence spec FR-038a.
    """
    output = "\n".join(child.lines)
    lowered = output.lower()

    if "no index found" in lowered:
        return {
            "kind": "index_missing",
            "message": "That repository has no stored analysis yet, or it is unusable. Analyse it to rebuild.",
            "detail": child.tail(),
        }
    if "no provider in the" in lowered and "chain is currently available" in lowered:
        chain = None
        for candidate in ("embeddings", "summary", "chat"):
            if f"'{candidate}'" in output:
                chain = candidate
                break
        named = f"the '{chain}' provider chain" if chain else "a required provider chain"
        return {
            "kind": "provider_unavailable",
            "chain": chain,
            "message": (
                f"No provider in {named} is available, so this repository cannot be served. "
                "Its documentation is intact - this is a provider problem, not a problem with "
                "the analysis."
            ),
            "detail": child.tail(),
        }
    if "address may already be in use" in lowered or "could not start the server" in lowered:
        return {
            "kind": "bind_failed",
            "message": "Could not start another local server - no free port was available.",
            "detail": child.tail(),
        }
    return {
        "kind": "failed",
        "message": "The repository could not be opened.",
        "detail": child.tail(),
    }
