"""REST client handling, including StackExchangeStream base class."""

from typing import Any, Dict, Iterable, List, Optional

import requests
from ratelimit import RateLimitException, limits, sleep_and_retry
from requests_cache import install_cache
from singer_sdk.streams import RESTStream


def has_backoff(response: requests.Response):
    """Check if response sets the `backoff` field."""
    return "backoff" not in response.text


install_cache(expire_after=3600, filter_fn=has_backoff)  # 1 hour
limiter = limits(calls=60, period=60)


class StackExchangeStream(RESTStream):
    """StackExchange stream class."""

    PAGE_SIZE = 100
    url_base = "https://api.stackexchange.com/2.3"
    records_jsonpath = "$.items[*]"

    @property
    def http_headers(self) -> dict:
        """Return the http headers needed."""
        headers = {}
        if "user_agent" in self.config:
            headers["User-Agent"] = self.config.get("user_agent")
        return headers

    @sleep_and_retry
    @limiter
    def _request_with_backoff(
        self,
        prepared_request: requests.PreparedRequest,
        context: Optional[dict],
    ) -> requests.Response:
        response = super()._request_with_backoff(prepared_request, context)
        if "backoff" in response.text:
            self.logger.debug(response.text)
            backoff = response.json()["backoff"]
            raise RateLimitException("Backoff triggered", backoff)
        return response

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        """Return a dictionary of values to be used in URL parameterization."""
        params = {
            "site": self.config["site"],
            "key": self.config["key"],
            "pagesize": self.PAGE_SIZE,
            "order": "asc",
            "sort": "activity",
        }

        if next_page_token:
            params["page"] = next_page_token

        if self.replication_key:
            params["fromdate"] = self.get_starting_replication_key_value(context)

        return params

    def get_next_page_token(
        self, response: requests.Response, previous_token: Optional[Any]
    ) -> Any:
        has_more = response.json()["has_more"]
        previous_token = previous_token or 1

        if has_more:
            return previous_token + 1
        else:
            return None

    @property
    def partitions(self) -> Optional[List[dict]]:
        return [{"tag": tag} for tag in self.config.get("tags", [])]
