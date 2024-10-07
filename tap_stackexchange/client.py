"""REST client handling, including StackExchangeStream base class."""

from __future__ import annotations

import json
import logging
import typing as t

from pyrate_limiter import (
    Duration,
    Limiter,
    LimiterDelayException,
    Rate,
    RateItem,
    TimeClock,
)
from requests_cache import install_cache
from singer_sdk.exceptions import RetriableAPIError
from singer_sdk.pagination import BasePageNumberPaginator
from singer_sdk.streams import RESTStream

if t.TYPE_CHECKING:
    import requests
    from singer_sdk.helpers.types import Context

logger = logging.getLogger(__name__)

BASE_URL = "https://api.stackexchange.com/2.3"


def has_backoff(response: requests.Response) -> bool:
    """Check if response sets the `backoff` field.

    Args:
        response: HTTP response.

    Returns:
        True if the response contains a rate limiting backoff amount.
    """
    try:
        return "backoff" in response.json()
    except json.JSONDecodeError:
        return False


install_cache(expire_after=3600, filter_fn=lambda r: not has_backoff(r))  # 1 hour
rate = Rate(100, Duration.MINUTE)
limiter = Limiter(rate, max_delay=100_000)


class StackExchangeStream(RESTStream):
    """StackExchange stream class."""

    PAGE_SIZE = 100
    METRICS_LOG_LEVEL_SETTING = "DEBUG"
    CUSTOM_FILTER_INCLUDE: t.ClassVar[list[str]] = [
        "question.comment_count",
        "tag.last_activity_date",
    ]

    records_jsonpath = "$.items[*]"
    is_sorted = True

    rate_limit_response_codes: t.ClassVar[list[int]] = []

    def __init__(self, *args: t.Any, base_url: str = BASE_URL, **kwargs: t.Any) -> None:
        """Initialize the stream.

        Args:
            *args: Positional arguments for RESTStream.
            base_url: Base URL for the API.
            **kwargs: Keyword arguments for RESTStream.
        """
        self.base_url = base_url
        super().__init__(*args, **kwargs)

    @property
    def url_base(self) -> str:
        """API base URL.

        Returns:
            Base URL.
        """
        return self.base_url

    @property
    def http_headers(self) -> dict:
        """Return the http headers needed.

        Returns:
            Mapping of HTTP headers.
        """
        headers = {}
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config.get("user_agent")
        return headers

    def request_decorator(self, func: t.Callable) -> t.Callable:
        """Decorate the request method of the stream.

        Args:
            func: The RESTStream._request method.

        Returns:
            Decorated method.
        """
        return limiter.as_decorator()(self._limiter_mapping)(func)

    def _limiter_mapping(self, *_args: t.Any, **_kwargs: t.Any) -> tuple[str, int]:
        return self.tap_name, 1

    def validate_response(self, response: requests.Response) -> None:
        """Validate the HTTP response.

        Args:
            response: HTTP response.

        Raises:
            LimiterDelayException: if a backoff amount is returned with the response
                or any other recoverable error occurs.
        """
        if has_backoff(response):
            self.logger.info(response.text)
            backoff = response.json()["backoff"]
            self.logger.info("BACKOFF: %s", backoff)
            clock = TimeClock()
            raise LimiterDelayException(
                item=RateItem(
                    self.tap_name,
                    clock.now(),
                ),
                rate=rate,
                actual_delay=backoff,
                max_delay=100_000,
            )

        try:
            super().validate_response(response)
        except RetriableAPIError as exc:
            self.logger.info("TEXT: %s", response.text)
            clock = TimeClock()
            raise LimiterDelayException(
                item=RateItem(
                    self.tap_name,
                    clock.now(),
                ),
                rate=rate,
                actual_delay=5_000,
                max_delay=100_000,
            ) from exc

    def get_url_params(
        self,
        context: Context | None,
        next_page_token: int | None,
    ) -> dict[str, t.Any]:
        """Return a dictionary of values to be used in URL parameterization.

        Args:
            context: Stream context dictionary.
            next_page_token: Value used to retrieve next page of data.

        Returns:
            Mapping of URL query parameters.
        """
        params = {
            "site": self.config["site"],
            "pagesize": self.PAGE_SIZE,
            "order": "asc",
            "sort": "activity",
            "filter": self.config["filter"],
        }

        if self.config.get("key"):
            params["key"] = self.config["key"]

        if next_page_token:
            params["page"] = next_page_token

        if self.replication_key:
            params["fromdate"] = self.get_starting_replication_key_value(context)

        return params

    def get_new_paginator(self) -> BasePageNumberPaginator:
        """Return a new paginator instance.

        Returns:
            Paginator instance.
        """
        return BasePageNumberPaginator(start_value=1)


class TagPartitionedStream(StackExchangeStream):
    """Tag-partitioned stream class."""

    @property
    def partitions(self) -> list[dict[str, t.Any]] | None:
        """Partition stream by the configured tags.

        Returns:
            List of dictionary representing different partitions in the stream.
        """
        return [{"tag": tag} for tag in self.config.get("tags", [])]
