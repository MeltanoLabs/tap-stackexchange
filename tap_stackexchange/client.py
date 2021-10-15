"""REST client handling, including StackExchangeStream base class."""

import requests
from typing import Any, Dict, Optional, List, Iterable

from requests_cache import install_cache
from ratelimit import limits, sleep_and_retry

from singer_sdk.streams import RESTStream

install_cache(expire_after=3600)  # 1 hour


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
    @limits(calls=15, period=1.0)
    def _request_with_backoff(
        self,
        prepared_request: requests.PreparedRequest,
        context: Optional[dict],
    ) -> requests.Response:
        return super()._request_with_backoff(prepared_request, context)

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

    def post_process(self, row: dict, context) -> dict:
        user = row.pop("user", {})
        if user and user["user_type"] != "does_not_exist":
            row["user_id"] = user["user_id"]
            row["account_id"] = user["account_id"]

        owner = row.pop("owner", {})
        if owner and owner["user_type"] != "does_not_exist":
            row["owner_user_id"] = owner["user_id"]
            row["owner_account_id"] = owner["account_id"]

        reply_to_user = row.pop("reply_to_user", {})
        if reply_to_user and reply_to_user["user_type"] != "does_not_exist":
            row["reply_to_user_user_id"] = reply_to_user["user_id"]
            row["reply_to_user_account_id"] = reply_to_user["account_id"]

        return super().post_process(row, context)
