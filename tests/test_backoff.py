"""Test that backoff values are handled correctly."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pyrate_limiter import LimiterDelayException

from tap_stackexchange.streams import Tags
from tap_stackexchange.tap import TapStackExchange

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer


def test_explicit_backoff(httpserver: HTTPServer) -> None:
    """Test that a backoff value is handled correctly."""
    base_url = httpserver.url_for("/")
    httpserver.expect_oneshot_request("/tags").respond_with_json(
        {
            "backoff": 10,
            "items": [],
        },
    )

    tags = Tags(
        tap=TapStackExchange(),
        base_url=base_url,
    )

    with pytest.raises(LimiterDelayException):
        next(tags.get_records(None))


def test_error_backoff(httpserver: HTTPServer) -> None:
    """Test that a 500 response with a backoff value is handled correctly."""
    base_url = httpserver.url_for("/")
    httpserver.expect_oneshot_request("/tags").respond_with_json(
        {
            "items": [],
        },
        status=500,
    )

    tags = Tags(
        tap=TapStackExchange(),
        base_url=base_url,
    )

    with pytest.raises(LimiterDelayException):
        next(tags.get_records(None))
