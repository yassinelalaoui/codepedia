"""The narrative cache in `doc-manifest.sqlite` (038 data-model, persistent state)."""

from __future__ import annotations

import sqlite3

from doc_generator.manifest_store import open_doc_manifest_store

REPO = "repo-1"


def test_save_then_load_by_key_round_trips_reply_and_handle_map(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative(REPO, "key-a", '{"lead": ["x"]}', {"f0": "feature-a", "f1": "feature-b"})

    assert store.load_overview_narrative(REPO, "key-a") == (
        '{"lead": ["x"]}',
        {"f0": "feature-a", "f1": "feature-b"},
    )


def test_load_with_a_different_key_is_a_miss(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative(REPO, "key-a", "reply", {})

    assert store.load_overview_narrative(REPO, "key-b") is None
    assert store.load_overview_narrative("another-repo", "key-a") is None


def test_load_latest_ignores_the_key(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative(REPO, "key-a", "reply-a", {"f0": "x"})

    assert store.load_latest_overview_narrative(REPO) == ("reply-a", {"f0": "x"})
    assert store.load_latest_overview_narrative("another-repo") is None


def test_save_overwrites_the_single_row_per_repository(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative(REPO, "key-a", "reply-a", {})
    store.save_overview_narrative(REPO, "key-b", "reply-b", {"f0": "y"})

    assert store.load_overview_narrative(REPO, "key-a") is None
    assert store.load_latest_overview_narrative(REPO) == ("reply-b", {"f0": "y"})
    with sqlite3.connect(tmp_path / "m.sqlite") as connection:
        (count,) = connection.execute("SELECT COUNT(*) FROM doc_overview_narratives").fetchone()
    assert count == 1


def test_unreadable_handle_map_json_is_a_miss_not_a_crash(tmp_path):
    store = open_doc_manifest_store(tmp_path / "m.sqlite")
    store.save_overview_narrative(REPO, "key-a", "reply", {})
    with sqlite3.connect(tmp_path / "m.sqlite") as connection:
        connection.execute("UPDATE doc_overview_narratives SET handle_map_json = 'not json'")

    assert store.load_overview_narrative(REPO, "key-a") is None
    assert store.load_latest_overview_narrative(REPO) is None


def test_schema_appears_on_an_existing_database_without_migration(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE doc_pages (page_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, kind TEXT NOT NULL,"
            " source_symbol_ids TEXT NOT NULL, linked_page_ids TEXT NOT NULL, content_hash TEXT NOT NULL,"
            " output_path_markdown TEXT NOT NULL, output_path_html TEXT NOT NULL, last_generated_at TEXT NOT NULL)"
        )

    store = open_doc_manifest_store(db_path)
    store.save_overview_narrative(REPO, "key", "reply", {})

    assert store.load_overview_narrative(REPO, "key") == ("reply", {})
