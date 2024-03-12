"""StackExchange tap class."""

from __future__ import annotations

from singer_sdk import Stream, Tap
from singer_sdk import typing as th

from tap_stackexchange import streams

FILTER_ID = "!6VvPDzOeLJfUL"

STREAM_TYPES = [
    streams.Questions,
    streams.QuestionAnswers,
    streams.QuestionComments,
    streams.Tags,
    streams.TagSynonyms,
    streams.TopAnswerers,
    streams.TopAskers,
]


class TapStackExchange(Tap):
    """Singer tap for the StackExchange API."""

    name = "tap-stackexchange"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "key",
            th.StringType,
            required=False,
            description="Pass this to receive a higher request quota",
        ),
        th.Property(
            "filter",
            th.StringType,
            required=False,
            description="Custom API filter to apply to all requests",
            default=FILTER_ID,
        ),
        th.Property(
            "site",
            th.StringType,
            default="stackoverflow.com",
            description="StackExchange site",
        ),
        th.Property(
            "tags",
            th.ArrayType(th.StringType),
            default=[],
            description="Question tags",
        ),
        th.Property(
            "start_date",
            th.IntegerType,
            description="The earliest record date to sync",
        ),
    ).to_dict()

    def discover_streams(self) -> list[Stream]:
        """Return a list of discovered streams.

        Returns:
            List of stream instances.
        """
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]
