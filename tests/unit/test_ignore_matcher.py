from pathlib import Path

from repo_scanner.ignore import load_ignore_matcher


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_negation_re_includes_a_previously_ignored_file(tmp_path: Path):
    _write(tmp_path / ".gitignore", "*.log\n!keep.log\n")

    matcher = load_ignore_matcher(tmp_path)

    assert matcher.ignores("debug.log") is True
    assert matcher.ignores("keep.log") is False


def test_nested_gitignore_overrides_the_root_one(tmp_path: Path):
    _write(tmp_path / ".gitignore", "*.log\n")
    _write(tmp_path / "sub" / ".gitignore", "!*.log\ndata/\n")

    matcher = load_ignore_matcher(tmp_path)

    assert matcher.ignores("root.log") is True
    assert matcher.ignores("sub/kept.log") is False
    assert matcher.ignores("sub/data", is_dir=True) is True
    assert matcher.ignores("sub/data/values.json") is True


def test_directory_only_and_anchored_patterns_follow_git_semantics(tmp_path: Path):
    _write(tmp_path / ".gitignore", "cache/\n/top.txt\nsrc/generated\n")

    matcher = load_ignore_matcher(tmp_path)

    assert matcher.ignores("cache", is_dir=True) is True
    assert matcher.ignores("cache/entry.bin") is True
    assert matcher.ignores("cache.txt") is False
    assert matcher.ignores("top.txt") is True
    assert matcher.ignores("nested/top.txt") is False
    assert matcher.ignores("src/generated/api.ts") is True


def test_default_excluded_dirs_apply_without_a_gitignore(tmp_path: Path):
    matcher = load_ignore_matcher(tmp_path)

    assert matcher.ignores("node_modules/pkg/index.js") is True
    assert matcher.ignores("build/output.txt") is True
    assert matcher.ignores("src/app.py") is False


def test_gitignore_negation_wins_over_default_excluded_dirs(tmp_path: Path):
    _write(tmp_path / ".gitignore", "!build/keep.txt\n")

    matcher = load_ignore_matcher(tmp_path)

    assert matcher.ignores("build/keep.txt") is False
    assert matcher.ignores("build/other.txt") is True


def test_extra_patterns_are_applied_at_the_repository_root(tmp_path: Path):
    matcher = load_ignore_matcher(tmp_path, extra_patterns=("*.snap",))

    assert matcher.ignores("tests/render.snap") is True
    assert matcher.ignores("tests/render.ts") is False


def test_invalidate_makes_a_rewritten_gitignore_take_effect(tmp_path: Path):
    """`serve` builds one matcher at startup and holds it for the life of the
    process, so without this a `.gitignore` edited while the server runs had no
    effect at all until a restart."""
    _write(tmp_path / ".gitignore", "*.log\n")
    matcher = load_ignore_matcher(tmp_path)
    assert matcher.ignores("debug.log") is True

    _write(tmp_path / ".gitignore", "*.tmp\n")
    assert matcher.ignores("debug.log") is True  # still the cached spec

    matcher.invalidate()

    assert matcher.ignores("debug.log") is False
    assert matcher.ignores("scratch.tmp") is True


def test_invalidate_also_forgets_nested_gitignores(tmp_path: Path):
    _write(tmp_path / ".gitignore", "*.log\n")
    _write(tmp_path / "pkg" / ".gitignore", "!keep.log\n")
    matcher = load_ignore_matcher(tmp_path)
    assert matcher.ignores("pkg/keep.log") is False

    _write(tmp_path / "pkg" / ".gitignore", "*.log\n")
    matcher.invalidate()

    assert matcher.ignores("pkg/keep.log") is True
