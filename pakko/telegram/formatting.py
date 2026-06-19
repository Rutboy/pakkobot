import html
import re
from collections.abc import Iterable

TELEGRAM_LIMIT = 4096
TELEGRAM_HTML_LIMIT = 3900

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
LINK_RE = re.compile(r"\[([^\]]+)]\((https?://[^\s)]+)\)")


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
    for match in LINK_RE.finditer(text):
        parts.append(_format_bold(match.string[cursor : match.start()]))
        label = _format_bold(match.group(1))
        url = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{url}">{label}</a>')
        cursor = match.end()
    parts.append(_format_bold(text[cursor:]))
    return "".join(parts)


def _format_bold(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return BOLD_RE.sub(r"<b>\1</b>", escaped)