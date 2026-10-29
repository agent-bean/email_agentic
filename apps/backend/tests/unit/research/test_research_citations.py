
import pytest

from email_agentic.workflows.research import canonical_url, cited_urls


def test_malformed_source_url_is_rejected_without_crashing_validation():
    assert canonical_url("http://[invalid") is None


@pytest.mark.parametrize("text", [
    "[Source](https://example.com/entry_(detail))",
    "See https://example.com/entry_(detail).",
    "See <https://example.com/entry_(detail)>.",
])
def test_source_validation_covers_bare_and_markdown_links_with_balanced_url_parentheses(text):
    assert cited_urls(text) == {"https://example.com/entry_(detail)"}
