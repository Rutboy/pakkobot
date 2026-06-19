from collections.abc import Iterable

TELEGRAM_LIMIT = 4096


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
