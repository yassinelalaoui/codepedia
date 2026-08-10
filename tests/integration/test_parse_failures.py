from pathlib import Path

from parser_engine import (
    GoParser,
    JavaParser,
    JavaScriptParser,
    ParseResult,
    PythonParser,
    RustParser,
    SourceFile,
    TypeScriptParser,
    parse_batch,
)


def test_batch_continues_after_failure():
    files = [
        SourceFile(path=Path("ok.py"), language="python", content="def ok():\n    return 1\n"),
        SourceFile(path=Path("bad.py"), language="python", content="def missing_colon()\n    pass\n"),
        SourceFile(path=Path("ok.js"), language="javascript", content="function ok() { return 1; }\n"),
    ]
    results = parse_batch(files)
    assert len(results) == 3
    assert results[0].success is True
    assert results[1].success is False
    assert results[2].success is True


def test_supported_language_parsers_produce_results():
    parsers = [
        PythonParser(),
        JavaScriptParser(),
        TypeScriptParser(),
        JavaParser(),
        GoParser(),
        RustParser(),
    ]
    files = [
        SourceFile(path=Path("a.py"), language="python", content="class A:\n    pass\n"),
        SourceFile(path=Path("a.js"), language="javascript", content="function a() { return 1; }\n"),
        SourceFile(path=Path("a.ts"), language="typescript", content="interface A { value: string }\n"),
        SourceFile(path=Path("a.java"), language="java", content="class A { }\n"),
        SourceFile(path=Path("a.go"), language="go", content="package main\nfunc main() {}\n"),
        SourceFile(path=Path("a.rs"), language="rust", content="fn main() {}\n"),
    ]
    results = [parser.parse_result(file) for parser, file in zip(parsers, files, strict=True)]
    assert all(result.success for result in results)

