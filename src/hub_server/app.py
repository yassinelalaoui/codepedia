"""The hub's HTTP surface (contracts/hub-http-api.md).

Built as its own FastAPI app rather than by extending `chat_api.create_app`.
The two share no routes and no state, and leaving `create_app` untouched is what
makes spec FR-002 cheap to hold (research.md §9).

The static mount is registered last, so every API route above wins. It is
deliberately unguarded, matching `chat_api`'s reasoning: the bundle and the
brand assets are public files, while everything that is not - starting a run,
opening a repository, deleting an analysis - sits behind the token.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

import typer
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import StreamingResponse

from chat_api.security import DEFAULT_ALLOWED_HOSTS

from . import children, history, run_log
from .paths import InvalidRepositoryPathError, validate_submitted_path
from .runs import CANCELLED, FAILED, SUCCEEDED, RunState
from .security import UnauthorizedError, require_hub_token, require_hub_token_or_query

ASSETS_DIR = Path(__file__).parent / "assets"

# How often the stream re-reads the run's version counter. Comfortably inside
# spec SC-002's two seconds and spec SC-011's one minute, and simpler than
# bridging the reader thread to the event loop (research.md §4).
STREAM_POLL_SECONDS = 0.25
STREAM_HEARTBEAT_SECONDS = 15.0

# How long Open waits for a child server to print its URL. Generous, because a
# catch-up re-index runs before that line appears and can take minutes.
SERVER_READY_TIMEOUT = 600.0
# How long Open waits before deciding there is catch-up work worth showing. If
# the URL arrives inside this, the person goes straight to the wiki and no
# progress display is ever drawn (spec FR-020).
QUICK_OPEN_SECONDS = 4.0


def _error(kind: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"kind": kind, "message": message}}, status_code=status)


class HubState:
    """Everything one hub process owns. Not shared, not persisted."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.currentRun: Optional[RunState] = None
        self.currentChild: Optional[children.ChildProcess] = None
        self.servers: dict[str, children.ChildProcess] = {}
        self.runLog = run_log.RunLog()

    # -- runs ---------------------------------------------------------------

    def has_active_run(self) -> bool:
        with self.lock:
            return self.currentRun is not None and not self.currentRun.isTerminal

    def start_run(self, *, kind: str, repository_path: str, args: list[str], state_id: str | None = None) -> RunState:
        run = RunState(runId=uuid.uuid4().hex, kind=kind, repositoryPath=repository_path)
        with self.lock:
            self.currentRun = run
        self.runLog.append(run_id=run.runId, repository_path=repository_path, kind=kind)

        def on_event(event) -> None:  # noqa: ANN001 - ProgressEvent
            """Apply the event, and end an `open` run once its server is up.

            An `index` run ends when its process ends. An `open` run does not:
            the child it starts *is* the wiki server, so waiting for that child
            to exit means waiting for the reader to close the wiki. Its actual
            job - get a server listening and report the URL - is finished the
            moment `server_ready` arrives.

            Leaving it non-terminal had three visible consequences, all the same
            bug: the homepage kept redirecting back to the wiki because a run
            with a `serverUrl` looked live, no new analysis could be started
            because one was apparently already running, and the run log kept a
            row that a later startup would sweep as interrupted.
            """
            run.apply(event)
            if kind == "open" and event.type == "server_ready" and not run.isTerminal:
                run.finish(SUCCEEDED)
                self._record_outcome(run)

        child = children.launch(
            kind=kind,
            args=args,
            repository_path=repository_path,
            on_event=on_event,
            on_line=self._forward,
        )
        child.stateId = state_id
        run.childPid = child.pid
        with self.lock:
            self.currentChild = child

        threading.Thread(
            target=self._await_exit, args=(run, child), name=f"cp-run-{run.runId[:8]}", daemon=True
        ).start()
        return run

    @staticmethod
    def _forward(line: str) -> None:
        """A child's ordinary output is the hub's ordinary output (spec FR-016)."""
        typer.echo(line)

    def _await_exit(self, run: RunState, child: children.ChildProcess) -> None:
        """Turn the child's exit into the run's terminal state.

        The exit code decides, not the events: a child killed before it could
        emit anything still has to end the run (spec FR-021,
        contracts/run-progress-stream.md reader obligation 6).
        """
        code = child.process.wait()
        if run.isTerminal:
            # Already finished - a cancel got here first, or an `open` run
            # succeeded when its server came up. Its outcome is recorded
            # already, and spec FR-012a's cancelled outcome must not be
            # relabelled as a failure by the exit that cancelling caused.
            return

        if code == 0:
            run.finish(SUCCEEDED)
        else:
            message = run.failureMessage or (
                "The analysis stopped before it finished. Nothing was kept from this run."
            )
            run.finish("failed", message=message)
            # A non-zero exit may or may not have cleaned up after itself; a
            # crash or a kill does not. Removing this child's staging directory
            # keeps failures from accumulating residue the listing has to filter.
            children.discard_staging(run.repositoryPath, child.pid)

        self._record_outcome(run)

    def _record_outcome(self, run: RunState) -> None:
        self.runLog.close(
            run_id=run.runId,
            outcome=run.outcome or "failed",
            failed_stage=run.failedStage,
            failure_message=run.failureMessage,
            providers_attempted=run.providersAttempted,
        )

    def cancel_current(self) -> Optional[RunState]:
        with self.lock:
            run, child = self.currentRun, self.currentChild
        if run is None or run.isTerminal or child is None:
            return None

        # Terminal state first, so the exit watcher cannot relabel this as a
        # failure when the child dies a moment from now.
        run.finish(
            CANCELLED,
            message="You stopped this analysis. Nothing was kept from it.",
        )
        child.terminate()
        children.discard_staging(run.repositoryPath, child.pid)
        self._record_outcome(run)
        return run

    def shutdown(self) -> None:
        """Stop every child this hub started (spec FR-007)."""
        with self.lock:
            child, servers = self.currentChild, list(self.servers.values())
        if child is not None:
            child.terminate()
        for server in servers:
            server.terminate()


def create_hub_app(
    *,
    auth_token: str,
    host: str = "127.0.0.1",
    assets_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Codepedia", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.authToken = auth_token
    app.state.hub = HubState()

    allowed = list(DEFAULT_ALLOWED_HOSTS)
    if host not in allowed:
        allowed.append(host)
    # Spec FR-006: a page on another origin must not be able to reach this
    # server by pointing a domain at 127.0.0.1.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed)

    @app.exception_handler(UnauthorizedError)
    async def _unauthorized(_: Request, error: UnauthorizedError) -> JSONResponse:
        return _error("unauthorized", str(error), 401)

    def hub() -> HubState:
        return app.state.hub

    # -- starting an analysis ----------------------------------------------

    @app.post("/api/runs", status_code=202, dependencies=[Depends(require_hub_token)])
    async def start_run(request: Request) -> Any:
        body = await request.json() if await request.body() else {}
        try:
            resolved = validate_submitted_path(body.get("path", ""))
        except InvalidRepositoryPathError as error:
            # Nothing started, nothing written (spec FR-010).
            return _error(error.kind, str(error), 400)

        state = hub()
        if state.has_active_run():
            running = state.currentRun.repositoryPath if state.currentRun else "another repository"
            return _error(
                "run_in_progress",
                f"An analysis of {running} is already running. Only one runs at a time - "
                "wait for it to finish, or stop it first.",
                409,
            )

        run = state.start_run(
            kind="index",
            repository_path=str(resolved),
            args=["index", str(resolved)],
        )
        # The resolved path, not what was typed: the person should see what will
        # actually be analysed.
        return {"runId": run.runId, "repositoryPath": str(resolved)}

    @app.get("/api/runs/current", dependencies=[Depends(require_hub_token)])
    async def current_run() -> Any:
        run = hub().currentRun
        return {"run": run.snapshot() if run else None}

    @app.get("/api/runs/stream", dependencies=[Depends(require_hub_token_or_query)])
    async def run_stream() -> StreamingResponse:
        state = hub()

        async def events():
            last_version = -1
            idle = 0.0
            while True:
                run = state.currentRun
                snapshot = run.snapshot() if run else None
                version = snapshot["version"] if snapshot else -1
                if version != last_version:
                    last_version = version
                    idle = 0.0
                    yield f"data: {json.dumps({'run': snapshot})}\n\n"
                else:
                    idle += STREAM_POLL_SECONDS
                    if idle >= STREAM_HEARTBEAT_SECONDS:
                        idle = 0.0
                        # A comment frame: keeps a dropped connection
                        # detectable instead of silently hanging.
                        yield ": keep-alive\n\n"
                await asyncio.sleep(STREAM_POLL_SECONDS)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/current/cancel", dependencies=[Depends(require_hub_token)])
    async def cancel_run() -> Any:
        run = hub().cancel_current()
        if run is None:
            return _error("no_run", "There is no analysis running.", 409)
        return {"run": run.snapshot()}

    # The status code is set on the response rather than the decorator: these
    # handlers answer 204 on success and a JSON error otherwise, and FastAPI
    # refuses a declared 204 on a route that can carry a body.
    @app.post("/api/runs/current/dismiss", dependencies=[Depends(require_hub_token)])
    async def dismiss_run() -> Any:
        state = hub()
        with state.lock:
            run = state.currentRun
            if run is None:
                return Response(status_code=204)
            if not run.isTerminal:
                return _error(
                    "run_in_progress",
                    "That analysis is still running. Stop it instead of dismissing it.",
                    409,
                )
            state.currentRun = None
            state.currentChild = None
        return Response(status_code=204)

    # -- the analyse history ------------------------------------------------

    @app.get("/api/repositories", dependencies=[Depends(require_hub_token)])
    async def list_repositories() -> Any:
        return {"repositories": [entry.to_dict() for entry in history.list_entries()]}

    @app.post("/api/repositories/{state_id}/open", dependencies=[Depends(require_hub_token)])
    async def open_repository(state_id: str) -> Any:
        entry = history.find(state_id)
        if entry is None:
            return _error("not_found", "That repository is not in the history.", 404)

        state = hub()
        existing = state.servers.get(state_id)
        if existing is not None and existing.is_running() and existing.url:
            # Spec FR-037: repositories are independent, but one repository does
            # not need two servers.
            return {"url": existing.url}

        if state.has_active_run():
            running = state.currentRun.repositoryPath if state.currentRun else "another repository"
            return _error(
                "run_in_progress",
                f"An analysis of {running} is running. Wait for it to finish, or stop it first.",
                409,
            )

        port = children.free_port()
        run = state.start_run(
            kind="open",
            repository_path=entry.repositoryPath,
            args=["serve", entry.repositoryPath, "--host", "127.0.0.1", "--port", str(port)],
            state_id=state_id,
        )
        child = state.currentChild
        if child is None:  # pragma: no cover - start_run always sets it
            return _error("server_start_failed", "The server could not be started.", 502)
        child.port = port
        state.servers[state_id] = child

        # Wait briefly: a repository with nothing to catch up is ready almost at
        # once, and spec FR-020 says that person must never see a progress
        # display at all.
        url = await asyncio.to_thread(child.wait_for_url, QUICK_OPEN_SECONDS)
        if url:
            run.finish(SUCCEEDED)
            state._record_outcome(run)
            return {"url": url}

        if not child.is_running():
            failure = children.classify_failure(child)
            run.finish("failed", message=failure["message"])
            state._record_outcome(run)
            return _error("server_start_failed", failure["message"], 502)

        # Still working: there is catch-up to show (spec FR-019). The page
        # follows the stream and navigates when `server_ready` arrives.
        return JSONResponse({"runId": run.runId, "catchup": True}, status_code=202)

    @app.delete("/api/repositories/{state_id}", dependencies=[Depends(require_hub_token)])
    async def remove_repository(state_id: str) -> Any:
        entry = history.find(state_id)
        if entry is None:
            return _error("not_found", "That repository is not in the history.", 404)

        state = hub()
        run = state.currentRun
        if run is not None and not run.isTerminal and run.repositoryPath == entry.repositoryPath:
            # Spec FR-042: surface the conflict, never delete half of it.
            return _error(
                "conflict",
                "That repository is being analysed right now. Stop the analysis before removing it.",
                409,
            )
        server = state.servers.get(state_id)
        if server is not None and server.is_running():
            return _error(
                "conflict",
                "That repository is open in a running server. Close it before removing it.",
                409,
            )

        try:
            history.remove(state_id)
        except OSError as error:
            return _error("conflict", f"That repository's files could not be removed: {error}", 409)
        return Response(status_code=204)

    # -- the run log --------------------------------------------------------

    @app.get("/api/run-log", dependencies=[Depends(require_hub_token)])
    async def read_run_log() -> Any:
        # Never a 500: a missing or unreadable log means "no history", not a
        # broken homepage (spec FR-026e).
        return {"runs": [record.to_dict() for record in hub().runLog.recent()]}

    # -- the page -----------------------------------------------------------

    directory = assets_dir or ASSETS_DIR
    if directory.is_dir():
        # Last, so every route above wins.
        app.mount("/", StaticFiles(directory=str(directory), html=True), name="hub")

    return app
