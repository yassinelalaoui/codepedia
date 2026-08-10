from pathlib import Path

from parser_engine import SourceFile, parse_batch


def test_multi_language_batch_includes_one_failure():
    files = [
        SourceFile(path=Path("ok.py"), language="python", content="def ok():\n    return 1\n"),
        SourceFile(path=Path("ok.js"), language="javascript", content="function ok() { return 1; }\n"),
        SourceFile(path=Path("bad.rs"), language="rust", content="fn broken( {\n}\n"),
        SourceFile(path=Path("ok.go"), language="go", content="package main\nfunc main() {}\n"),
    ]
    results = parse_batch(files)
    assert [result.success for result in results] == [True, True, False, True]

