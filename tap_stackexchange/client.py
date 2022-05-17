"""REST client handling, including StackExchangeStream base class."""

import logging
from typing import Any, Callable, Dict, List, Optional

import requests
from ratelimit import RateLimitException, limits, sleep_and_retry
from requests_cache import install_cache
from singer_sdk.exceptions import RetriableAPIError
from singer_sdk.streams import RESTStream

logger = logging.getLogger(__name__)


def has_backoff(response: requests.Response):
    """Check if response sets the `backoff` field."""
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

    rate_limit_response_codes: List[int] = []

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
        if has_backoff(response):
            self.logger.info(response.text)
            backoff = response.json()["backoff"]
            raise RateLimitException("Retrying", backoff)

        try:
            super().validate_response(response)
        except RetriableAPIError as exc:
            raise RateLimitException("Backoff triggered", 5) from exc

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
