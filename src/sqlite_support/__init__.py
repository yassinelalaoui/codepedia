"""Write-path settings shared by every SQLite database this project opens.

There are four of them - the repository metadata store, the vector index, the
doc-page manifest and the dependency graph - and until now not one set a
`journal_mode` or a `synchronous` pragma anywhere in `src/`. Every commit
therefore paid a full fsync, which is what made an index write cost a flat
~23ms per chunk regardless of volume.

The constant lives here, in a package nothing else imports, for the reason
`prose.PROSE_FILE_SUFFIXES` did not: with a copy per package, raising
`synchronous` in one of them and not the others would produce two databases
with different durability and no error anywhere to say so.
"""

from __future__ import annotations

import sqlite3


__all__ = ["apply_write_pragmas"]


def apply_write_pragmas(connection: sqlite3.Connection) -> None:
    """Put `connection` in WAL with `synchronous=NORMAL`, if the file allows it.

    WAL is what makes a commit stop being an fsync: writers append to the
    `-wal` file and the database is only synced at a checkpoint. With
    `synchronous=NORMAL` the remaining exposure is an OS-level crash losing the
    most recent transactions - never a corrupt database - which for a
    regenerable index is the right trade.

    The cost is that WAL leaves `-wal` and `-shm` files beside the database,
    and `cli/index_command.py` renames a whole state directory into place on
    Windows. `checkpoint_and_close` below is the counterpart: the run
    checkpoints and closes before that rename, so nothing is left holding the
    directory.

    Failure is tolerated rather than raised. `journal_mode=WAL` cannot be set
    inside a transaction, is refused for an in-memory database, and can fail on
    a network filesystem that has no shared-memory support - none of which is a
    reason to refuse to open a database that otherwise works.
    """
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        pass


def checkpoint_and_close(connection: sqlite3.Connection) -> None:
    """Fold the `-wal` file back into the database, then close.

    Called before a state directory is renamed into place: a truncating
    checkpoint empties the `-wal`, and closing the last connection removes it
    and the `-shm` along with it.
    """
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    finally:
        connection.close()
