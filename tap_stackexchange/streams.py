"""Stream type classes for tap-stackexchange."""

import requests
from singer_sdk import typing as th

from tap_stackexchange.client import StackExchangeStream

SHALLOW_USER = th.ObjectType(
    th.Property("accept_rate", th.IntegerType),
    th.Property("account_id", th.IntegerType),
    th.Property("display_name", th.StringType),
    th.Property("link", th.StringType),
    th.Property("profile_image", th.StringType),
    th.Property("reputation", th.IntegerType),
    th.Property("user_id", th.IntegerType),
    th.Property("user_type", th.StringType),
)

SITE = th.ObjectType(
    th.Property("aliases", th.ArrayType(th.StringType)),
    th.Property("api_site_parameter", th.StringType),
    th.Property("audience", th.StringType),
    th.Property("closed_beta_date", th.IntegerType),
    th.Property("favicon_url", th.StringType),
    th.Property("high_resolution_icon_url", th.StringType),
    th.Property("high_resolution_icon_url", th.StringType),
    th.Property("launch_date", th.IntegerType),
    th.Property("logo_url", th.StringType),
    th.Property("markdown_extensions", th.ArrayType(th.StringType)),
    th.Property("name", th.StringType),
    th.Property("open_beta_date", th.IntegerType),
    th.Property("related_sites", th.ArrayType(th.StringType)),
    th.Property("site_state", th.StringType),
    th.Property("site_type", th.StringType),
    th.Property("site_url", th.StringType),
    th.Property(
        "styling",
        th.ObjectType(
            th.Property("link_color", th.StringType),
            th.Property("tag_background_color", th.StringType),
            th.Property("tag_foreground_color", th.StringType),
        ),
    ),
    th.Property("twitter_account", th.StringType),
)


class Questions(StackExchangeStream):
    """Questions stream."""

    name = "questions"
    path = "/questions"
    primary_keys = ["question_id"]
    replication_key = "last_activity_date"

    schema = th.PropertiesList(
        th.Property(
            "question_id",
            th.IntegerType,
            description="The question ID",
            required=True,
        ),
        th.Property("is_answered", th.BooleanType),
        th.Property("title", th.StringType),
        th.Property("last_activity_date", th.IntegerType),
        th.Property("creation_date", th.IntegerType),
        th.Property("last_edit_date", th.IntegerType),
        th.Property("tags", th.ArrayType(th.StringType)),
        th.Property("view_count", th.IntegerType),
        th.Property("answer_count", th.IntegerType),
        th.Property("content_license", th.StringType),
        th.Property("score", th.IntegerType),
        th.Property("link", th.StringType),
        th.Property("closed_date", th.IntegerType),
        th.Property("closed_reason", th.StringType),
        th.Property(
            "migrated_from",
            th.ObjectType(
                th.Property("on_date", th.IntegerType),
                th.Property("other_site", SITE),
                th.Property("question_id", th.IntegerType),
            ),
        ),
        th.Property("protected_date", th.IntegerType),
        th.Property("owner", SHALLOW_USER),
    ).to_dict()

    def get_url_params(self, context, next_page_token):
        params = super().get_url_params(context, next_page_token)
        params["tagged"] = context["tag"]
        return params

    def get_child_context(self, record: dict, context) -> dict:
        return {"question_id": record["question_id"]}


class QuestionAnswers(StackExchangeStream):
    """Question answers stream."""

    name = "answers"
    path = "/questions/{question_id}/answers"
    primary_keys = ["answer_id"]
    replication_key = "last_activity_date"
    parent_stream_type = Questions

    schema = th.PropertiesList(
        th.Property(
            "answer_id",
            th.IntegerType,
            description="The answer ID",
            required=True,
        ),
        th.Property(
            "question_id",
            th.IntegerType,
            description="The question ID",
            required=True,
        ),
        th.Property("is_accepted", th.BooleanType),
        th.Property("content_license", th.StringType),
        th.Property("creation_date", th.IntegerType),
        th.Property("last_activity_date", th.IntegerType),
        th.Property("last_edit_date", th.IntegerType),
        th.Property("score", th.IntegerType),
        th.Property("owner", SHALLOW_USER),
    ).to_dict()


class QuestionComments(StackExchangeStream):
    """Question comments stream."""

    name = "question_comments"
    path = "/questions/{question_id}/comments"
    primary_keys = ["comment_id"]
    replication_key = "creation_date"
    parent_stream_type = Questions

    schema = th.PropertiesList(
        th.Property("post_id", th.IntegerType, required=True),
        th.Property("comment_id", th.IntegerType, required=True),
        th.Property("edited", th.BooleanType),
        th.Property("content_license", th.StringType),
        th.Property("creation_date", th.IntegerType),
        th.Property("score", th.IntegerType),
        th.Property("owner", SHALLOW_USER),
        th.Property("reply_to_user", SHALLOW_USER),
    ).to_dict()

    def get_url_params(self, context, next_page_token):
        params = super().get_url_params(context, next_page_token)
        params["sort"] = "creation"
        return params


class TopAskers(StackExchangeStream):
    """Top askers for a tag."""

    name = "top_askers"
    path = "/tags/{tag}/top-askers/all_time"
    primary_keys = ["idx", "tag"]
    replication_key = None

    schema = th.PropertiesList(
        th.Property("user", SHALLOW_USER),
        th.Property("idx", th.IntegerType),
        th.Property("tag", th.StringType),
        th.Property("post_count", th.IntegerType),
        th.Property("score", th.IntegerType),
    ).to_dict()

    def parse_response(self, response: requests.Response):
        records = super().parse_response(response)
        for idx, record in enumerate(records):
            record["idx"] = idx
            yield record

    def post_process(self, row: dict, context) -> dict:
        row = super().post_process(row, context)
        row["tag"] = context["tag"]
        return row


class TopAnswerers(TopAskers):
    """Top answerers for a tag."""

    name = "top_answerers"
    path = "/tags/{tag}/top-answerers/all_time"


class TagSynonyms(StackExchangeStream):
    """Tag synonyms."""

    name = "tag_synonyms"
    path = "/tags/{tag}/synonyms"
    primary_keys = ["from_tag", "to_tag"]
    replication_key = "creation_date"

    schema = th.PropertiesList(
        th.Property("to_tag", th.StringType),
        th.Property("from_tag", th.StringType),
        th.Property("creation_date", th.IntegerType),
        th.Property("last_applied_date", th.IntegerType),
        th.Property("applied_count", th.IntegerType),
    ).to_dict()
