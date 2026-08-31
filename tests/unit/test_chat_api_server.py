from __future__ import annotations

from chat_api.security import (
    DEFAULT_ALLOWED_HOSTS,
    allowed_hosts_for,
    generate_token,
    is_loopback_host,
    startup_lines,
)
from chat_api.server import parse_args


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


def test_startup_lines_carry_the_token_in_the_url():
    # The wiki is a static bundle built before the server starts, so this URL is
    # the only channel this run's token has to reach the browser.
    lines = startup_lines("127.0.0.1", 8000, "sekret")

    assert lines[0] == "Documentation wiki available at http://127.0.0.1:8000/?token=sekret"
    assert len(lines) == 2


def test_a_non_loopback_bind_is_called_out():
    lines = startup_lines("192.168.1.20", 8000, "sekret")

    assert len(lines) == 3
    assert lines[2].startswith("WARNING: bound to 192.168.1.20")


def test_loopback_detection_covers_the_forms_a_user_types():
    assert is_loopback_host("127.0.0.1") is True
    assert is_loopback_host("localhost") is True
    assert is_loopback_host("::1") is True
    assert is_loopback_host("192.168.1.20") is False
    assert is_loopback_host("0.0.0.0") is False


def test_a_non_loopback_bind_is_added_to_the_allowed_hosts():
    # Otherwise TrustedHostMiddleware would refuse every request to the very
    # address the user asked to bind.
    assert allowed_hosts_for("192.168.1.20") == (*DEFAULT_ALLOWED_HOSTS, "192.168.1.20")
    assert allowed_hosts_for("127.0.0.1") == DEFAULT_ALLOWED_HOSTS
    # "every interface" is never sent as a Host header by a browser.
    assert allowed_hosts_for("0.0.0.0") == DEFAULT_ALLOWED_HOSTS


def test_each_generated_token_is_distinct():
    assert generate_token() != generate_token()
