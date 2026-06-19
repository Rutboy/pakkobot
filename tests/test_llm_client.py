from types import SimpleNamespace

from pakko.llm.client import OpenAIResponsesClient, normalize_source_url


def test_normalize_source_url_removes_tracking_params() -> None:
    assert (
        normalize_source_url("https://example.com/page?utm_source=x&ref=abc&id=42#section")
        == "https://example.com/page?id=42"
    )


def test_apply_inline_citations_links_annotated_text() -> None:
    text = "See Steam and PlayStation for details."
    annotations = [
        SimpleNamespace(start_index=4, end_index=9, url="https://store.steampowered.com/?utm_source=x"),
        SimpleNamespace(start_index=14, end_index=25, url="https://store.playstation.com/en-us/product/123"),
    ]

    assert OpenAIResponsesClient._apply_inline_citations(text, annotations) == (
        "See [Steam](https://store.steampowered.com/) and "
        "[PlayStation](https://store.playstation.com/en-us/product/123) for details."
    )


def test_apply_inline_citations_limits_inline_links() -> None:
    text = "one two three four five six"
    starts = [0, 4, 8, 14, 19, 24]
    words = ["one", "two", "three", "four", "five", "six"]
    annotations = [
        SimpleNamespace(start_index=start, end_index=start + len(word), url=f"https://example.com/{word}")
        for start, word in zip(starts, words, strict=True)
    ]

    linked = OpenAIResponsesClient._apply_inline_citations(text, annotations)

    assert linked.count("](") == 5
    assert "six" in linked
    assert "[six]" not in linked