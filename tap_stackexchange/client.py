"""REST client handling, including StackExchangeStream base class."""

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

import requests
from ratelimit import RateLimitException, limits
from requests_cache import install_cache
from singer_sdk.exceptions import RetriableAPIError
from singer_sdk.streams import RESTStream

logger = logging.getLogger(__name__)


def has_no_backoff(response: requests.Response):
    """Check if response sets the `backoff` field."""
    try:
        return "backoff" not in response.json()
    except Exception:
        return False


install_cache(expire_after=3600, filter_fn=has_no_backoff)  # 1 hour
limiter = limits(calls=100, period=60)


def sleep_and_retry(func: Callable) -> Callable:
    """Return a wrapped function that rescues rate limit exceptions.

    Sleeps until the rate limit resets.

    Args:
        func: The function to decorate.

    Returns:
        Decorated function.
    """

    @wraps(func)
    def _wrapper(*args, **kwargs):
        """Call the rate limited function.

        If the function raises a rate limit exception sleep for the remaining time
        period and retry the function.

        Args:
            args: Positional arguments of the decorated function.
            kwargs: Keyword arguments of the decorated function.
        """
        while True:
            try:
                return func(*args, **kwargs)
            except RateLimitException as exception:
                logger.debug("Sleeping for %s...", exception.period_remaining)
                time.sleep(exception.period_remaining)
            except RetriableAPIError as exception:
                logger.debug("Sleeping for 5", exc_info=exception)
                time.sleep(5)

    return _wrapper


class StackExchangeStream(RESTStream):
    """StackExchange stream class."""

    PAGE_SIZE = 100
    METRICS_LOG_LEVEL_SETTING = "DEBUG"
    url_base = "https://api.stackexchange.com/2.3"
    records_jsonpath = "$.items[*]"

    @property
    def http_headers(self) -> dict:
        """Return the http headers needed."""
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
        return sleep_and_retry(limiter(func))

    def validate_response(self, response: requests.Response) -> None:
        """Validate the HTTP response."""
        super().validate_response(response)
        if not has_no_backoff(response):
            self.logger.debug(response.text)
            backoff = response.json()["backoff"]
            raise RateLimitException("Backoff triggered", backoff)

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = {
            "site": self.config["site"],
            "pagesize": self.PAGE_SIZE,
            "order": "asc",
            "sort": "activity",
        }

        if "key" in self.config and self.config["key"]:
            params["key"] = self.config["key"]

        if next_page_token:
            params["page"] = next_page_token

        if self.replication_key:
            params["fromdate"] = self.get_starting_replication_key_value(context)

        return params

    def get_next_page_token(
        self, response: requests.Response, previous_token: Optional[Any]
    ) -> Any:
        """Get next page index from response."""
        has_more = response.json()["has_more"]
        previous_token = previous_token or 1

        if has_more:
            return previous_token + 1
        else:
            return None

    @property
    def partitions(self) -> Optional[List[dict]]:
        """Partition stream by the configured tags."""
        return [{"tag": tag} for tag in self.config.get("tags", [])]
