"""Test that backoff values are handled correctly."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from singer_sdk.exceptions import RetriableAPIError

from tap_stackexchange.streams import Tags
from tap_stackexchange.tap import TapStackExchange

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer


class _Tags(Tags):
    @override
    def backoff_max_tries(self) -> int:
        return 1


def test_explicit_backoff(httpserver: HTTPServer) -> None:
    """Test that a backoff value triggers a sleep and retry."""
    base_url = httpserver.url_for("/")
    httpserver.expect_oneshot_request("/tags").respond_with_json(
        {
            "backoff": 10,
            "items": [],
        },
    )

    tags = _Tags(
        tap=TapStackExchange(),
        base_url=base_url,
    )

    with (
        patch("tap_stackexchange.client.time.sleep") as mock_sleep,
        pytest.raises(RetriableAPIError),
    ):
        next(tags.get_records(None))  # type: ignore[call-overload]  # ty:ignore[invalid-argument-type]

    mock_sleep.assert_called_once_with(10)


def test_error_backoff(httpserver: HTTPServer) -> None:
    """Test that a 500 response raises RetriableAPIError."""
    base_url = httpserver.url_for("/")
    httpserver.expect_oneshot_request("/tags").respond_with_json(
        {
            "items": [],
        },
        status=500,
    )

    tags = _Tags(
        tap=TapStackExchange(),
        base_url=base_url,
    )

    with pytest.raises(RetriableAPIError):
        next(tags.get_records(None))  # type: ignore[call-overload]  # ty:ignore[invalid-argument-type]
