from __future__ import annotations

from pathlib import Path

_TEXT_BYTES = bytes(range(32, 127)) + b"\n\r\t\b\f"


def is_binary_path(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(sample_size)
    except OSError:
        return False
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    non_text = sum(1 for byte in chunk if byte not in _TEXT_BYTES)
    return (non_text / max(len(chunk), 1)) > 0.30

