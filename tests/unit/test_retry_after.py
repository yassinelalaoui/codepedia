"""`Retry-After` parsing, and the transports that read it.

`BackoffPolicy` used to guess how long a rate limit would last while both
remote providers were answering the 429 with the number. Nothing in `src/`
read the header at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from http_support import parse_retry_after


def _headers(value=None):
    return {} if value is None else {"Retry-After": value}


def test_a_delay_in_seconds_is_read_as_seconds():
    assert parse_retry_after(_headers("7")) == 7.0
    assert parse_retry_after(_headers(" 12 ")) == 12.0


def test_an_http_date_is_read_as_the_seconds_until_it():
    when = datetime.now(timezone.utc) + timedelta(seconds=30)

    seconds = parse_retry_after(_headers(format_datetime(when, usegmt=True)))

    assert seconds is not None
    assert 25.0 <= seconds <= 31.0


def test_a_date_already_past_clamps_to_zero():
    """"Wait no longer" is what it means. A negative floor would silently
    cancel the exponential term the caller adds on top."""
    when = datetime.now(timezone.utc) - timedelta(minutes=5)

    assert parse_retry_after(_headers(format_datetime(when, usegmt=True))) == 0.0


def test_a_negative_delay_clamps_to_zero():
    assert parse_retry_after(_headers("-3")) == 0.0


@pytest.mark.parametrize("value", [None, "", "   ", "soon", "2026-13-45"])
def test_an_absent_or_unreadable_header_means_keep_guessing(value):
    """A malformed header is a reason to fall back on the guess, never a reason
    to fail the call that was already failing."""
    assert parse_retry_after(_headers(value)) is None


def test_headers_that_will_not_answer_are_a_none():
    class _Hostile:
        def get(self, _name):
            raise RuntimeError("no")

    assert parse_retry_after(_Hostile()) is None
    assert parse_retry_after(None) is None
