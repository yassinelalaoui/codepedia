from __future__ import annotations

from .chain import ProviderChain, ProviderRef
from .classify import classify_failure
from .errors import FailoverExhaustedError
from .factory import build_chain_from_strings, build_stage_executor, resolve_chain
from .failover_log import FailoverLogEntry, PathFailoverLog, SqliteFailoverLog, append_failover_event, list_failover_events
from .router import BackoffNotifier, BackoffPolicy, FailoverAttempt, FailoverExecutor, FailoverLogWriter, FailoverResult

__all__ = [
    "BackoffNotifier",
    "BackoffPolicy",
    "FailoverAttempt",
    "FailoverExecutor",
    "FailoverExhaustedError",
    "FailoverLogEntry",
    "FailoverLogWriter",
    "FailoverResult",
    "PathFailoverLog",
    "ProviderChain",
    "ProviderRef",
    "SqliteFailoverLog",
    "append_failover_event",
    "build_chain_from_strings",
    "build_stage_executor",
    "classify_failure",
    "list_failover_events",
    "resolve_chain",
]
