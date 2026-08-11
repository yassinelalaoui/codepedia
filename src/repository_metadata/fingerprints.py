from __future__ import annotations

import hashlib
from pathlib import Path

from parser_engine import SourceFile


def compute_content_hash(source: SourceFile | Path | str) -> str:
    if isinstance(source, SourceFile):
        payload = source.read_text().encode("utf-8", errors="replace")
    else:
        payload = Path(source).read_bytes()
    return hashlib.sha256(payload).hexdigest()


def file_has_changed(stored_hash: str | None, current_hash: str) -> bool:
    if not stored_hash:
        return True
    return stored_hash != current_hash
