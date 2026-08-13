import threading
import time
from types import SimpleNamespace

import pytest

from repo_watcher.debouncer import Debouncer
from repo_watcher.models import ChangeBatch, ChangeType, FileChange
from repo_watcher.watcher import RepositoryWatcher
from repository_metadata import RepositoryMetadataStore
from repo_scanner.ignore import load_ignore_matcher

STABILIZATION_DELAY = 0.1


def _collect(timeout: float = 2.0):
    batches: list[ChangeBatch] = []
    event = threading.Event()

    def on_flush(batch: ChangeBatch) -> None:
        batches.append(batch)
        event.set()

    def wait() -> ChangeBatch:
        assert event.wait(timeout), "debouncer never flushed"
        return batches[-1]

    return on_flush, wait, batches


def test_change_batch_rejects_empty_changes():
    with pytest.raises(ValueError):
        ChangeBatch(changes=())


def test_change_batch_rejects_duplicate_paths():
    with pytest.raises(ValueError):
        ChangeBatch(
            changes=(
                FileChange(relative_path="a.py", change_type=ChangeType.CREATED),
                FileChange(relative_path="a.py", change_type=ChangeType.MODIFIED),
            )
        )


def test_debouncer_flushes_single_file_after_stabilization():
    on_flush, wait, _ = _collect()
    debouncer = Debouncer(stabilization_delay=STABILIZATION_DELAY, on_flush=on_flush)
    debouncer.notify("a.py", ChangeType.CREATED)
    batch = wait()
    assert batch.changes == (FileChange(relative_path="a.py", change_type=ChangeType.CREATED),)
    assert batch.origin == "live"


def test_debouncer_create_then_modify_stays_created():
    on_flush, wait, _ = _collect()
    debouncer = Debouncer(stabilization_delay=STABILIZATION_DELAY, on_flush=on_flush)
    debouncer.notify("a.py", ChangeType.CREATED)
    debouncer.notify("a.py", ChangeType.MODIFIED)
    batch = wait()
    assert batch.changes == (FileChange(relative_path="a.py", change_type=ChangeType.CREATED),)


def test_debouncer_create_then_delete_cancels(tmp_path):
    on_flush, _, batches = _collect()
    debouncer = Debouncer(stabilization_delay=STABILIZATION_DELAY, on_flush=on_flush)
    debouncer.notify("a.py", ChangeType.CREATED)
    debouncer.notify("a.py", ChangeType.DELETED)
    time.sleep(STABILIZATION_DELAY * 3)
    assert batches == []


def test_debouncer_excludes_binary_file_at_flush():
    on_flush, _, batches = _collect()
    debouncer = Debouncer(
        stabilization_delay=STABILIZATION_DELAY,
        on_flush=on_flush,
        is_binary=lambda path: path == "binary.dat",
    )
    debouncer.notify("binary.dat", ChangeType.CREATED)
    time.sleep(STABILIZATION_DELAY * 3)
    assert batches == []


def test_debouncer_groups_burst_of_settled_paths_into_one_batch():
    on_flush, wait, _ = _collect()
    debouncer = Debouncer(stabilization_delay=STABILIZATION_DELAY, on_flush=on_flush)
    for index in range(5):
        debouncer.notify(f"file{index}.py", ChangeType.CREATED)
    batch = wait()
    assert {change.relative_path for change in batch.changes} == {f"file{i}.py" for i in range(5)}


def test_ignore_matcher_excludes_relevant_looking_file_in_excluded_dir(tmp_path):
    (tmp_path / "node_modules").mkdir()
    matcher = load_ignore_matcher(tmp_path)
    assert matcher.ignores("node_modules/relevant.py", is_dir=False) is True


def test_repository_watcher_surfaces_on_batch_exception_via_on_error(tmp_path):
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    errors: list[BaseException] = []

    def failing_on_batch(batch: ChangeBatch) -> None:
        raise RuntimeError("boom")

    watcher = RepositoryWatcher(
        repository_root=tmp_path,
        on_batch=failing_on_batch,
        metadata_store=store,
        on_error=errors.append,
    )
    watcher._handle_batch(ChangeBatch(changes=(FileChange(relative_path="a.py", change_type=ChangeType.CREATED),)))
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_repository_watcher_health_check_reports_inaccessible_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    store = RepositoryMetadataStore(tmp_path / "metadata.sqlite")
    errors: list[BaseException] = []
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=lambda batch: None,
        metadata_store=store,
        on_error=errors.append,
    )
    watcher._observer = SimpleNamespace(stop=lambda: None, join=lambda: None)
    repo.rmdir()
    watcher._run_health_check()
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
