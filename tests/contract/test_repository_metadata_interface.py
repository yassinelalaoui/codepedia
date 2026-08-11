from pathlib import Path

from repository_metadata import (
    RepositoryMetadataStore,
    compute_content_hash,
    file_has_changed,
    open_repository_metadata_store,
)


def test_repository_metadata_public_api_is_available():
    store = open_repository_metadata_store(Path("repo.sqlite"))
    assert isinstance(store, RepositoryMetadataStore)
    assert hasattr(store, "ensure_repository")
    assert hasattr(store, "store_inventory")
    assert hasattr(store, "load_repository")
    assert hasattr(store, "load_source_file")
    assert hasattr(store, "has_file_changed")


def test_fingerprint_helpers_are_available():
    assert callable(compute_content_hash)
    assert file_has_changed(None, "abc") is True
    assert file_has_changed("abc", "abc") is False
