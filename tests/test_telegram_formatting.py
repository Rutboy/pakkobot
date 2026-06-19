from pakko.telegram.formatting import markdown_to_telegram_html, split_markdown_as_telegram_html


def test_markdown_to_telegram_html_formats_headings_and_bold() -> None:
    assert markdown_to_telegram_html("### Что важно\n**Факт**") == "<b>Что важно</b>\n<b>Факт</b>"


def test_markdown_to_telegram_html_escapes_plain_html() -> None:
    assert markdown_to_telegram_html("<script>**x**</script>") == "&lt;script&gt;<b>x</b>&lt;/script&gt;"


def test_split_markdown_as_telegram_html_returns_html_chunks() -> None:
    chunks = list(split_markdown_as_telegram_html("### Заголовок"))
    assert chunks == ["<b>Заголовок</b>"]


def test_markdown_to_telegram_html_strips_nested_bold_in_heading() -> None:
    assert markdown_to_telegram_html("### **Что важно**") == "<b>Что важно</b>"