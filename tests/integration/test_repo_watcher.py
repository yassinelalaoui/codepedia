from __future__ import annotations

import threading
import time
from pathlib import Path

from parser_engine import SourceFile, extract_symbols
from repo_watcher import ChangeBatch, ChangeType, FileChange, RepositoryWatcher
from repository_metadata import RepositoryMetadataStore, compute_content_hash

STABILIZATION_DELAY = 0.3
WAIT_TIMEOUT = 6.0
STARTUP_SETTLE = 0.2


def _make_store(tmp_path: Path) -> RepositoryMetadataStore:
    return RepositoryMetadataStore(tmp_path / "metadata.sqlite")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "node_modules").mkdir()
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    return repo


def _index_file(store: RepositoryMetadataStore, repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    source_file = SourceFile(path=path, language="python")
    inventory = extract_symbols(source_file)
    store.ensure_repository(repo, detected_languages=("python",))
    store.store_inventory(
        repository_root=repo,
        source_file=source_file,
        inventory=inventory,
        content_hash=compute_content_hash(path),
    )


class _BatchCollector:
    def __init__(self) -> None:
        self.batches: list[ChangeBatch] = []
        self._lock = threading.Lock()

    def __call__(self, batch: ChangeBatch) -> None:
        with self._lock:
            self.batches.append(batch)

    def wait_for_count(self, count: int, timeout: float = WAIT_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.batches) >= count:
                    return
            time.sleep(0.02)
        raise AssertionError(f"Timed out waiting for {count} batches; got {len(self.batches)}")

    def assert_stable_count(self, count: int, wait: float) -> None:
        time.sleep(wait)
        with self._lock:
            assert len(self.batches) == count, self.batches


def test_create_modify_delete_each_produce_a_batch(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        target = repo / "src" / "module.py"
        target.write_text("value = 1\n", encoding="utf-8")
        collector.wait_for_count(1)
        assert collector.batches[0].origin == "live"
        assert collector.batches[0].changes == (FileChange("src/module.py", ChangeType.CREATED),)

        target.write_text("value = 2\n", encoding="utf-8")
        collector.wait_for_count(2)
        assert collector.batches[1].changes == (FileChange("src/module.py", ChangeType.MODIFIED),)

        target.unlink()
        collector.wait_for_count(3)
        assert collector.batches[2].changes == (FileChange("src/module.py", ChangeType.DELETED),)
    finally:
        watcher.stop()


def test_rename_yields_delete_and_create_in_one_batch(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    old_path = repo / "src" / "old_name.py"
    _index_file(store, repo, "src/old_name.py", "value = 1\n")
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        new_path = repo / "src" / "new_name.py"
        old_path.rename(new_path)
        collector.wait_for_count(1)
        collector.assert_stable_count(1, wait=STABILIZATION_DELAY * 2)
        changes = {change.relative_path: change.change_type for change in collector.batches[0].changes}
        assert changes == {
            "src/old_name.py": ChangeType.DELETED,
            "src/new_name.py": ChangeType.CREATED,
        }
    finally:
        watcher.stop()


def test_startup_catchup_reports_offline_changes(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    _index_file(store, repo, "src/keep.py", "def keep():\n    return 1\n")
    _index_file(store, repo, "src/remove.py", "def gone():\n    return 1\n")

    (repo / "src" / "keep.py").write_text("def keep():\n    return 2\n", encoding="utf-8")
    (repo / "src" / "remove.py").unlink()

    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    try:
        collector.wait_for_count(1)
        batch = collector.batches[0]
        assert batch.origin == "catchup"
        changes = {change.relative_path: change.change_type for change in batch.changes}
        assert changes == {
            "src/keep.py": ChangeType.MODIFIED,
            "src/remove.py": ChangeType.DELETED,
        }
    finally:
        watcher.stop()


def test_startup_catchup_reports_newly_excluded_file_as_deleted(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    _index_file(store, repo, "src/legacy.py", "def legacy():\n    return 1\n")

    (repo / ".gitignore").write_text("node_modules/\nsrc/legacy.py\n", encoding="utf-8")

    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    try:
        collector.wait_for_count(1)
        batch = collector.batches[0]
        assert batch.origin == "catchup"
        changes = {change.relative_path: change.change_type for change in batch.changes}
        assert changes == {"src/legacy.py": ChangeType.DELETED}
    finally:
        watcher.stop()


def test_startup_catchup_first_run_reports_everything_as_created(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    (repo / "src" / "alpha.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "src" / "beta.py").write_text("value = 2\n", encoding="utf-8")

    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    try:
        collector.wait_for_count(1)
        batch = collector.batches[0]
        assert batch.origin == "catchup"
        changes = {change.relative_path: change.change_type for change in batch.changes}
        assert changes == {
            "src/alpha.py": ChangeType.CREATED,
            "src/beta.py": ChangeType.CREATED,
        }
    finally:
        watcher.stop()


def test_normal_file_operations_are_not_blocked_while_watching(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=lambda batch: None,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    start = time.monotonic()
    watcher.start()
    startup_duration = time.monotonic() - start
    try:
        assert startup_duration < 1.0

        op_start = time.monotonic()
        for index in range(20):
            path = repo / "src" / f"file{index}.py"
            path.write_text(f"value = {index}\n", encoding="utf-8")
            assert path.read_text(encoding="utf-8") == f"value = {index}\n"
            path.unlink()
        op_duration = time.monotonic() - op_start
        assert op_duration < 5.0
    finally:
        watcher.stop()


def test_rapid_saves_of_same_file_collapse_to_one_batch(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        target = repo / "src" / "hot.py"
        for index in range(5):
            target.write_text(f"value = {index}\n", encoding="utf-8")
            time.sleep(0.02)
        collector.wait_for_count(1)
        collector.assert_stable_count(1, wait=STABILIZATION_DELAY * 2)
        assert len(collector.batches[0].changes) == 1
        assert collector.batches[0].changes[0].relative_path == "src/hot.py"
    finally:
        watcher.stop()


def test_bulk_change_touching_many_files_yields_one_batch(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        for index in range(10):
            (repo / "src" / f"bulk{index}.py").write_text(f"value = {index}\n", encoding="utf-8")
        collector.wait_for_count(1)
        collector.assert_stable_count(1, wait=STABILIZATION_DELAY * 2)
        assert {change.relative_path for change in collector.batches[0].changes} == {f"src/bulk{i}.py" for i in range(10)}
    finally:
        watcher.stop()


def test_excluded_paths_never_produce_a_batch(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        (repo / "node_modules" / "pkg.py").write_text("value = 1\n", encoding="utf-8")
        collector.assert_stable_count(0, wait=STABILIZATION_DELAY * 3)
    finally:
        watcher.stop()


def test_mixed_burst_reports_only_the_relevant_file(tmp_path):
    repo = _make_repo(tmp_path)
    store = _make_store(tmp_path)
    collector = _BatchCollector()
    watcher = RepositoryWatcher(
        repository_root=repo,
        on_batch=collector,
        metadata_store=store,
        stabilization_delay=STABILIZATION_DELAY,
    )
    watcher.start()
    time.sleep(STARTUP_SETTLE)
    try:
        (repo / "node_modules" / "pkg.py").write_text("value = 1\n", encoding="utf-8")
        (repo / "src" / "relevant.py").write_text("value = 2\n", encoding="utf-8")
        collector.wait_for_count(1)
        collector.assert_stable_count(1, wait=STABILIZATION_DELAY * 2)
        assert collector.batches[0].changes == (FileChange("src/relevant.py", ChangeType.CREATED),)
    finally:
        watcher.stop()
