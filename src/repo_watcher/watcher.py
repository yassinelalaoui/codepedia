from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from repo_scanner.binary import is_binary_path
from repo_scanner.ignore import load_ignore_matcher
from repo_scanner.scanner import os_accessible
from repository_metadata import RepositoryMetadataStore

from .debouncer import Debouncer
from .models import ChangeBatch, ChangeType
from .reconciliation import compute_catchup_batch


class RepositoryWatcher:
    def __init__(
        self,
        *,
        repository_root: str | Path,
        on_batch: Callable[[ChangeBatch], None],
        metadata_store: RepositoryMetadataStore,
        stabilization_delay: float = 1.5,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        root = Path(repository_root).expanduser().resolve()
        _validate_repository_root(root)
        self._repository_root = root
        self._on_batch = on_batch
        self._metadata_store = metadata_store
        self._stabilization_delay = stabilization_delay
        self._on_error = on_error
        self._ignore_matcher = load_ignore_matcher(root)
        self._debouncer = Debouncer(
            stabilization_delay=stabilization_delay,
            on_flush=self._handle_batch,
            is_binary=self._is_binary,
        )
        self._observer: Observer | None = None
        self._health_timer: threading.Timer | None = None

    def isRunning(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        catchup_batch = compute_catchup_batch(self._repository_root, self._metadata_store)
        if catchup_batch is not None:
            self._handle_batch(catchup_batch)
        handler = _ChangeEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self._repository_root), recursive=True)
        observer.start()
        self._observer = observer
        self._schedule_health_check()

    def stop(self) -> None:
        if self._health_timer is not None:
            self._health_timer.cancel()
            self._health_timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._debouncer.cancel_all()

    def _is_binary(self, relative_path: str) -> bool:
        return is_binary_path(self._repository_root / relative_path)

    def _handle_batch(self, batch: ChangeBatch) -> None:
        try:
            self._on_batch(batch)
        except Exception as exc:  # noqa: BLE001 - surfaced via on_error, must not crash the loop
            self._report_error(exc)

    def _notify_raw_event(self, relative_path: str, change_type: ChangeType, *, is_dir: bool) -> None:
        if self._ignore_matcher.ignores(relative_path, is_dir=is_dir):
            return
        self._debouncer.notify(relative_path, change_type)

    def _handle_raw_event(self, absolute_path: str, change_type: ChangeType) -> None:
        try:
            relative_path = Path(absolute_path).resolve().relative_to(self._repository_root).as_posix()
        except ValueError:
            return
        self._notify_raw_event(relative_path, change_type, is_dir=False)

    def _schedule_health_check(self) -> None:
        interval = max(self._stabilization_delay, 2.0)
        timer = threading.Timer(interval, self._run_health_check)
        timer.daemon = True
        self._health_timer = timer
        timer.start()

    def _run_health_check(self) -> None:
        if self._observer is None:
            return
        if not self._repository_root.exists() or not os_accessible(self._repository_root):
            self._report_error(RuntimeError(f"Repository is no longer accessible: {self._repository_root}"))
            self.stop()
            return
        self._schedule_health_check()

    def _report_error(self, exc: BaseException) -> None:
        if self._on_error is not None:
            self._on_error(exc)
        else:
            traceback.print_exc()


def _validate_repository_root(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    if not os_accessible(root):
        raise PermissionError(f"Repository path is not readable: {root}")


class _ChangeEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: RepositoryWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher._handle_raw_event(event.src_path, ChangeType.CREATED)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher._handle_raw_event(event.src_path, ChangeType.MODIFIED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher._handle_raw_event(event.src_path, ChangeType.DELETED)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher._handle_raw_event(event.src_path, ChangeType.DELETED)
        self._watcher._handle_raw_event(event.dest_path, ChangeType.CREATED)
