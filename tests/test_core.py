"""Tests standard tap features using the built-in SDK tests library."""

from __future__ import annotations

from singer_sdk.testing import SuiteConfig, get_tap_test_class

from tap_stackexchange.tap import TapStackExchange

SAMPLE_CONFIG = {
    "site": "stackoverflow",
    "tags": [
        "meltano",
        "singer-io",
    ],
}

TEST_SUITE_CONFIG = SuiteConfig(
    ignore_no_records_for_streams=["tag_synonyms"],
    max_records_limit=15,
)

TestTapStackExchange = get_tap_test_class(
    tap_class=TapStackExchange,
    config=SAMPLE_CONFIG,
    suite_config=TEST_SUITE_CONFIG,
)
