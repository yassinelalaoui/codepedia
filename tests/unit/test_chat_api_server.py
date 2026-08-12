from __future__ import annotations

from chat_api.server import _startup_message, parse_args


def test_default_host_is_loopback_only():
    args = parse_args(["--repo", ".", "--llm-model", "llama3", "--docs-root", "docs"])

    assert args.host == "127.0.0.1"


def test_explicit_host_override_is_honored():
    args = parse_args(
        ["--repo", ".", "--llm-model", "llama3", "--docs-root", "docs", "--host", "192.168.1.20"]
    )

    assert args.host == "192.168.1.20"


def test_docs_root_argument_is_stored():
    args = parse_args(["--repo", ".", "--llm-model", "llama3", "--docs-root", "some/path"])

    assert args.docs_root == "some/path"


def test_startup_message_states_the_wiki_address():
    message = _startup_message("127.0.0.1", 8000)

    assert message == "Documentation wiki available at http://127.0.0.1:8000/"
