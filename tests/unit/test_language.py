from pathlib import Path

from repo_scanner.language import LanguageDetector


def test_language_detector_uses_extensions(tmp_path: Path):
    py_file = tmp_path / "module.py"
    py_file.write_text("print('hi')\n", encoding="utf-8")
    assert LanguageDetector().detect(py_file) == "Python"


def test_language_detector_maps_js_and_java(tmp_path: Path):
    js_file = tmp_path / "app.js"
    java_file = tmp_path / "Main.java"
    js_file.write_text("console.log('x')\n", encoding="utf-8")
    java_file.write_text("class Main {}\n", encoding="utf-8")
    detector = LanguageDetector()
    assert detector.detect(js_file) == "JavaScript"
    assert detector.detect(java_file) == "Java"

