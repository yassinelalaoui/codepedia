import inspect

from repo_watcher import RepositoryWatcher


def test_repository_watcher_exposes_lifecycle_methods():
    assert callable(RepositoryWatcher.start)
    assert callable(RepositoryWatcher.stop)
    assert callable(RepositoryWatcher.isRunning)


def test_repository_watcher_constructor_accepts_contract_parameters():
    parameters = inspect.signature(RepositoryWatcher.__init__).parameters
    assert "repository_root" in parameters
    assert "on_batch" in parameters
    assert "stabilization_delay" in parameters
    assert parameters["stabilization_delay"].default != inspect.Parameter.empty
