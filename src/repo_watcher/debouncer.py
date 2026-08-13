from __future__ import annotations

import threading
from typing import Callable

from .models import ChangeBatch, ChangeType, FileChange

IsBinaryCheck = Callable[[str], bool]


def _merge(previous: ChangeType | None, incoming: ChangeType) -> ChangeType | None:
    if previous is None:
        return incoming
    if previous == ChangeType.CREATED:
        return None if incoming == ChangeType.DELETED else ChangeType.CREATED
    if previous == ChangeType.MODIFIED:
        return ChangeType.DELETED if incoming == ChangeType.DELETED else ChangeType.MODIFIED
    if previous == ChangeType.DELETED:
        return ChangeType.MODIFIED if incoming != ChangeType.DELETED else ChangeType.DELETED
    return incoming


class Debouncer:
    def __init__(
        self,
        *,
        stabilization_delay: float,
        on_flush: Callable[[ChangeBatch], None],
        is_binary: IsBinaryCheck | None = None,
    ) -> None:
        self._stabilization_delay = stabilization_delay
        self._on_flush = on_flush
        self._is_binary = is_binary
        self._lock = threading.Lock()
        self._pending: dict[str, ChangeType] = {}
        self._active_timers: dict[str, threading.Timer] = {}

    def notify(self, relative_path: str, change_type: ChangeType) -> None:
        with self._lock:
            merged = _merge(self._pending.get(relative_path), change_type)
            self._cancel_timer_locked(relative_path)
            if merged is None:
                self._pending.pop(relative_path, None)
                return
            self._pending[relative_path] = merged
            timer = threading.Timer(self._stabilization_delay, self._on_path_settled, args=(relative_path,))
            timer.daemon = True
            self._active_timers[relative_path] = timer
            timer.start()

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._active_timers.values():
                timer.cancel()
            self._active_timers.clear()
            self._pending.clear()

    def _cancel_timer_locked(self, relative_path: str) -> None:
        timer = self._active_timers.pop(relative_path, None)
        if timer is not None:
            timer.cancel()

    def _on_path_settled(self, relative_path: str) -> None:
        batch: ChangeBatch | None = None
        with self._lock:
            self._active_timers.pop(relative_path, None)
            if self._active_timers or not self._pending:
                return
            changes: list[FileChange] = []
            for path in sorted(self._pending):
                change_type = self._pending[path]
                if change_type in (ChangeType.CREATED, ChangeType.MODIFIED) and self._is_binary is not None and self._is_binary(path):
                    continue
                changes.append(FileChange(relative_path=path, change_type=change_type))
            self._pending.clear()
            if changes:
                batch = ChangeBatch(changes=tuple(changes), origin="live")
        if batch is not None:
            self._on_flush(batch)
