import html
import re
from collections.abc import Iterable

TELEGRAM_LIMIT = 4096
TELEGRAM_HTML_LIMIT = 3900

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def split_for_telegram(text: str, limit: int = TELEGRAM_LIMIT) -> Iterable[str]:
    if len(text) <= limit:
        yield text
        return

    remaining = text
    while remaining:
        chunk = remaining[:limit]
        split_at = max(chunk.rfind("\n"), chunk.rfind(". "), chunk.rfind(" "))
        if split_at < limit // 2:
            split_at = limit
        yield remaining[:split_at].strip()
        remaining = remaining[split_at:].strip()


def markdown_to_telegram_html(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        heading = HEADING_RE.match(raw_line)
        if heading:
            title = BOLD_RE.sub(r"\1", heading.group(1))
            lines.append(f"<b>{html.escape(title, quote=False)}</b>")
            continue
        lines.append(_format_inline(raw_line))
    return "\n".join(lines).strip()


def split_markdown_as_telegram_html(text: str) -> Iterable[str]:
    for chunk in split_for_telegram(text, TELEGRAM_HTML_LIMIT):
        yield markdown_to_telegram_html(chunk)


def _format_inline(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        link = _find_next_markdown_link(text, cursor)
        if link is None:
            parts.append(_format_bold(text[cursor:]))
            break

        start, end, label, url = link
        parts.append(_format_bold(text[cursor:start]))
        formatted_label = _format_bold(label)
        escaped_url = html.escape(url, quote=True)
        parts.append(f'<a href="{escaped_url}">{formatted_label}</a>')
        cursor = end

    return "".join(parts)


def _find_next_markdown_link(text: str, start_at: int) -> tuple[int, int, str, str] | None:
    search_from = start_at
    while True:
        label_start = text.find("[", search_from)
        if label_start == -1:
            return None

        label_end = text.find("](", label_start + 1)
        if label_end == -1:
            return None

        label = text[label_start + 1 : label_end]
        url_start = label_end + 2
        if not text.startswith(("http://", "https://"), url_start):
            search_from = label_start + 1
            continue

        parsed = _parse_markdown_url(text, url_start)
        if parsed is None:
            search_from = label_start + 1
            continue

        url_end, url = parsed
        return label_start, url_end + 1, label, url


def _parse_markdown_url(text: str, url_start: int) -> tuple[int, str] | None:
    depth = 0
    cursor = url_start
    while cursor < len(text):
        char = text[cursor]
        if char.isspace() or char in "<>":
            return None
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                url = text[url_start:cursor]
                return (cursor, url) if url else None
            depth -= 1
        cursor += 1
    return None


def _format_bold(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return BOLD_RE.sub(r"<b>\1</b>", escaped)
