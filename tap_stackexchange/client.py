"""REST client handling, including StackExchangeStream base class."""

from __future__ import annotations

import logging
from typing import Any, Callable

import requests
from ratelimit import RateLimitException, limits, sleep_and_retry
from requests_cache import install_cache
from singer_sdk.exceptions import RetriableAPIError
from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.streams import RESTStream

logger = logging.getLogger(__name__)


def has_backoff(response: requests.Response) -> bool:
    """Check if response sets the `backoff` field.

    Args:
        response: HTTP response.

    Returns:
        True if the response contains a rate limiting backoff amount.
    """
    try:
        return "backoff" in response.json()
    except Exception:
        return False


install_cache(expire_after=3600, filter_fn=lambda r: not has_backoff(r))  # 1 hour
limiter = limits(calls=100, period=60)


class StackExchangeStream(RESTStream):
    """StackExchange stream class."""

    PAGE_SIZE = 100
    METRICS_LOG_LEVEL_SETTING = "DEBUG"
    url_base = "https://api.stackexchange.com/2.3"
    records_jsonpath = "$.items[*]"

    rate_limit_response_codes: list[int] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the stream.

        Args:
            *args: Positional arguments for RESTStream.
            **kwargs: Keyword arguments for RESTStream.
        """
        super().__init__(*args, **kwargs)
        self._custom_filter = None

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

    @property
    def custom_filter_id(self) -> str | None:
        """Return the custom filter id.

        Returns:
            Custom filter id.
        """
        if self._custom_filter is None:
            request = self.build_prepared_request(
                method="GET",
                url=f"{self.url_base}/filters/create",
                params={
                    "include": "question.comment_count",
                    "exclude": "",
                    "unsafe": "false",
                },
            )
            response = self.requests_session.send(request)
            self._custom_filter = next(
                extract_jsonpath("$.items[*].filter", response.json()),
                None,
            )
        return self._custom_filter

    def request_decorator(self, func: Callable) -> Callable:
        """Decorate the request method of the stream.

        Args:
            func: The RESTStream._request method.

        Returns:
            Decorated method.
        """
        return sleep_and_retry(limiter(func))

    def validate_response(self, response: requests.Response) -> None:
        """Validate the HTTP response.

        Args:
            response: HTTP response.

        Raises:
            RateLimitException: if a backoff amount is returned with the response
                or any other recoverable error occurs.
        """
        if has_backoff(response):
            self.logger.info(response.text)
            backoff = response.json()["backoff"]
            self.logger.info("BACKOFF: %s", backoff)
            raise RateLimitException("Retrying", backoff)

        try:
            super().validate_response(response)
        except RetriableAPIError as exc:
            raise RateLimitException("Backoff triggered", 5) from exc

    def get_url_params(
        self,
        context: dict | None,
        next_page_token: Any | None,
    ) -> dict[str, Any]:
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
            "filter": self.custom_filter_id,
        }

        if "key" in self.config and self.config["key"]:
            params["key"] = self.config["key"]

        if next_page_token:
            params["page"] = next_page_token

        if self.replication_key:
            params["fromdate"] = self.get_starting_replication_key_value(context)

        return params

    def get_next_page_token(
        self, response: requests.Response, previous_token: Any | None
    ) -> Any:
        """Get next page index from response.

        Args:
            response: HTTP response.
            previous_token: Previous pagination token.

        Returns:
            Next pagination token.
        """
        has_more = response.json()["has_more"]
        previous_token = previous_token or 1

        if has_more:
            return previous_token + 1
        else:
            return None

    @property
    def partitions(self) -> list[dict] | None:
        """Partition stream by the configured tags.

        Returns:
            List of dictionary representing different partitions in the stream.
        """
        return [{"tag": tag} for tag in self.config.get("tags", [])]
