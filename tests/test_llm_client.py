from types import SimpleNamespace

from pakko.llm.client import LLMInputAttachment, OpenAIResponsesClient, normalize_source_url


def test_normalize_source_url_removes_tracking_params() -> None:
    assert (
        normalize_source_url("https://example.com/page?utm_source=x&ref=abc&id=42#section")
        == "https://example.com/page?id=42"
    )


def test_apply_inline_citations_links_annotated_text() -> None:
    text = "See Steam and PlayStation for details."
    annotations = [
        SimpleNamespace(
            start_index=4,
            end_index=9,
            url="https://store.steampowered.com/?utm_source=x",
        ),
        SimpleNamespace(
            start_index=14,
            end_index=25,
            url="https://store.playstation.com/en-us/product/123",
        ),
    ]

    assert OpenAIResponsesClient._apply_inline_citations(text, annotations) == (
        "See [Steam](https://store.steampowered.com/) and "
        "[PlayStation](https://store.playstation.com/en-us/product/123) for details."
    )


def test_apply_inline_citations_limits_inline_links() -> None:
    text = "one two three four five six"
    words = ["one", "two", "three", "four", "five", "six"]
    starts = [text.index(word) for word in words]
    annotations = [
        SimpleNamespace(
            start_index=start,
            end_index=start + len(word),
            url=f"https://example.com/{word}",
        )
        for start, word in zip(starts, words, strict=True)
    ]

    linked = OpenAIResponsesClient._apply_inline_citations(text, annotations)

    assert linked.count("](") == 5
    assert "six" in linked
    assert "[six]" not in linked


def test_apply_inline_citations_flattens_existing_markdown_link() -> None:
    text = (
        "Use ([platform.openai.com](https://platform.openai.com/docs?utm_source=openai)) "
        "for docs."
    )
    end_index = text.index(" for docs.")
    annotations = [
        SimpleNamespace(
            start_index=4,
            end_index=end_index,
            url="https://platform.openai.com/docs?api-mode=responses&utm_source=openai",
        )
    ]

    assert OpenAIResponsesClient._apply_inline_citations(text, annotations) == (
        "Use [platform.openai.com](https://platform.openai.com/docs?api-mode=responses) for docs."
    )

def test_input_attachment_builds_image_content_item() -> None:
    attachment = LLMInputAttachment(
        filename="photo.jpg",
        mime_type="image/jpeg",
        data=b"image-bytes",
    )

    assert attachment.to_content_item() == {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM=",
    }


def test_input_attachment_builds_file_content_item() -> None:
    attachment = LLMInputAttachment(
        filename="report.pdf",
        mime_type="application/pdf",
        data=b"pdf-bytes",
    )

    assert attachment.to_content_item() == {
        "type": "input_file",
        "filename": "report.pdf",
        "file_data": "data:application/pdf;base64,cGRmLWJ5dGVz",
    }
