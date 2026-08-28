from __future__ import annotations

import threading

from vector_index import CodeChunk, VectorIndex
from vector_index.search import encode_text


class FakeEmbeddingEngine:
    def embed(self, text: str):
        return encode_text(text)


def _run_off_thread(work) -> BaseException | None:
    """Run `work()` on another thread and hand back whatever it raised."""
    captured: list[BaseException] = []

    def target() -> None:
        try:
            work()
        except BaseException as exc:  # noqa: BLE001 - the point is to capture it
            captured.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    return captured[0] if captured else None


def _chunk(chunk_id: str, path: str = "alpha.py") -> CodeChunk:
    return CodeChunk(
        id=chunk_id,
        content="value = 1",
        embedding=encode_text("value = 1"),
        sourceSymbolId=f"symbol_{chunk_id}",
        sourceFilePath=path,
    )


def test_a_write_from_another_thread_does_not_raise(tmp_path):
    """`serve` writes from the watcher's timer thread, not the thread that opened the index.

    `repo_watcher`'s debouncer fires on a `threading.Timer`, which reaches
    `reindexFile` through the reindex pipeline, while `VectorIndex` was
    constructed on the main thread by `serve_command`. The watcher swallows the
    failure into `on_error`, so this only ever showed up as a silently skipped
    batch.
    """
    index = VectorIndex(tmp_path, tmp_path / "meta.sqlite")

    error = _run_off_thread(lambda: index.addChunk(_chunk("c1")))

    assert error is None, f"cross-thread write raised {type(error).__name__}: {error}"
    assert len(index) == 1


def test_a_search_from_another_thread_does_not_raise(tmp_path):
    """The chat API serves searches from uvicorn's loop thread.

    Search reads an in-memory snapshot today, so this passes trivially; it is
    here to hold the line once retrieval starts touching SQL.
    """
    index = VectorIndex(
        tmp_path, tmp_path / "meta.sqlite", embedding_engine=FakeEmbeddingEngine()
    )
    index.addChunk(_chunk("c1"))

    error = _run_off_thread(lambda: index.search("value", 1))

    assert error is None, f"cross-thread search raised {type(error).__name__}: {error}"


def test_concurrent_writes_from_several_threads_all_land(tmp_path):
    """Serialized access must not drop writes when threads overlap."""
    index = VectorIndex(tmp_path, tmp_path / "meta.sqlite")
    errors: list[BaseException] = []

    def writer(number: int) -> None:
        try:
            index.addChunk(_chunk(f"c{number}", path=f"file{number}.py"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(number,)) for number in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(index) == 8
