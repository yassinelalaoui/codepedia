from pathlib import Path

from repo_scanner.binary import is_binary_path


def test_binary_detection_flags_null_bytes(tmp_path: Path):
    binary_file = tmp_path / "blob.bin"
    binary_file.write_bytes(b"\x00\x01\x02\x03")
    assert is_binary_path(binary_file) is True


def test_binary_detection_accepts_text(tmp_path: Path):
    text_file = tmp_path / "file.txt"
    text_file.write_text("hello world\n", encoding="utf-8")
    assert is_binary_path(text_file) is False

