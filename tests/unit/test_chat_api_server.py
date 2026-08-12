from __future__ import annotations

from chat_api.server import parse_args


def test_default_host_is_loopback_only():
    args = parse_args(["--repo", ".", "--llm-model", "llama3"])

    assert args.host == "127.0.0.1"


def test_explicit_host_override_is_honored():
    args = parse_args(["--repo", ".", "--llm-model", "llama3", "--host", "192.168.1.20"])

    assert args.host == "192.168.1.20"
