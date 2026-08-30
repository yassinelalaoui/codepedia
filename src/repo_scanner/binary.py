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
    decoded = _decode_utf8_sample(chunk)
    if decoded is not None:
        # Counting *characters* rather than bytes is what makes this correct for
        # UTF-8 prose. Every non-ASCII character costs 2-4 bytes, so the byte
        # ratio alone rejected ordinary text: measured on this heuristic, an
        # emoji-heavy README scored 31% and a table drawn with box characters
        # 80%, both over the 0.30 threshold - they were silently dropped as
        # binary. Accented French sat at 15%, uncomfortably close. Anything that
        # decodes as UTF-8 is text; only control characters count against it.
        control = sum(1 for character in decoded if _is_control_character(character))
        return (control / max(len(decoded), 1)) > 0.30
    # Not valid UTF-8: could be latin-1 text or a real binary, so fall back to
    # the byte heuristic, which is what this function always did.
    non_text = sum(1 for byte in chunk if byte not in _TEXT_BYTES)
    return (non_text / max(len(chunk), 1)) > 0.30


def _decode_utf8_sample(chunk: bytes) -> str | None:
    """Decode `chunk` as UTF-8, tolerating a sequence cut by the sample boundary.

    Reading a fixed number of bytes can slice a multi-byte character in half, so
    up to three trailing bytes are dropped before giving up on the decode.
    """
    for trim in range(0, 4):
        candidate = chunk[: len(chunk) - trim] if trim else chunk
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None


def _is_control_character(character: str) -> bool:
    if character in "\n\r\t\b\f":
        return False
    codepoint = ord(character)
    return codepoint < 32 or codepoint == 127

