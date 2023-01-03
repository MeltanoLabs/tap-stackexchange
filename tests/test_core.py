"""Tests standard tap features using the built-in SDK tests library."""

from singer_sdk.testing import get_tap_test_class

from tap_stackexchange.tap import TapStackExchange

SAMPLE_CONFIG = {
    "site": "stackoverflow",
    "tags": [
        "meltano",
        "singer-io",
    ],
    "metrics_log_level": "debug",
}

TestTapStackExchange = get_tap_test_class(
    tap_class=TapStackExchange,
    config=SAMPLE_CONFIG,
    parse_env_config=True,
)
