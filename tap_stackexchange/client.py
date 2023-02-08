"""REST client handling, including StackExchangeStream base class."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

import requests
from pyrate_limiter import BucketFullException, Duration, Limiter, RequestRate
from requests_cache import install_cache
from singer_sdk.exceptions import RetriableAPIError
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
rate = RequestRate(100, Duration.MINUTE)
limiter = Limiter(rate)


class StackExchangeStream(RESTStream):
    """StackExchange stream class."""

    PAGE_SIZE = 100
    METRICS_LOG_LEVEL_SETTING = "DEBUG"
    CUSTOM_FILTER_INCLUDE = [
        "question.comment_count",
        "tag.last_activity_date",
    ]

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

    def request_decorator(self, func: Callable) -> Callable:
        """Decorate the request method of the stream.

        Args:
            func: The RESTStream._request method.

        Returns:
            Decorated method.
        """
        return limiter.ratelimit(self.tap_name, delay=True, max_delay=600)(func)

    def validate_response(self, response: requests.Response) -> None:
        """Validate the HTTP response.

        Args:
            response: HTTP response.

        Raises:
            BucketFullException: if a backoff amount is returned with the response
                or any other recoverable error occurs.
        """
        if has_backoff(response):
            self.logger.info(response.text)
            backoff = response.json()["backoff"]
            self.logger.info("BACKOFF: %s", backoff)
            raise BucketFullException(self.tap_name, rate, backoff)

        try:
            super().validate_response(response)
        except RetriableAPIError as exc:
            raise BucketFullException(self.tap_name, rate, 5) from exc

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
            "filter": self.config["filter"],
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

    # overridden to test _MAX_RECORDS_LIMIT
    def get_records(self, context: dict | None) -> Iterable[dict[str, Any]]:
        """Return a generator of record-type dictionary objects.

        Each record emitted should be a dictionary of property names to their values.

        Args:
            context: Stream partition or context dictionary.

        Yields:
            One item per (possibly processed) record in the API.
        """
        index = 1
        for record in self.request_records(context):
            transformed_record = self.post_process(record, context)
            if transformed_record is None:
                # Record filtered out during post_process()
                continue

            if (
                self._MAX_RECORDS_LIMIT
                and index < self._MAX_RECORDS_LIMIT
                or not self._MAX_RECORDS_LIMIT
            ):
                index += 1
                yield transformed_record
            else:
                # if we have reached the max records limit, return early
                break


class TagPartitionedStream(StackExchangeStream):
    """Tag-partitioned stream class."""

    @property
    def partitions(self) -> list[dict] | None:
        """Partition stream by the configured tags.

        Returns:
            List of dictionary representing different partitions in the stream.
        """
        return [{"tag": tag} for tag in self.config.get("tags", [])]
