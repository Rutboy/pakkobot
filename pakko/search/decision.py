import re

SEARCH_PATTERNS = [
    r"\blatest\b",
    r"\brecent\b",
    r"\bnews\b",
    r"\btoday\b",
    r"\bcurrent(?:ly)?\b",
    r"\bnow\b",
    r"\bofficial\b",
    r"\bsource\b",
    r"\bsources\b",
    r"\bstatistics?\b",
    r"\bmarket\b",
    r"\bprice\b",
    r"\brate\b",
    r"\bverify\b",
    r"\bfact[- ]?check\b",
    r"актуальн",
    r"новост",
    r"сегодня",
    r"последн",
    r"сейчас",
    r"на данный момент",
    r"кто сейчас",
    r"официальн",
    r"найди",
    r"поищи",
    r"интернет",
    r"ссылк",
    r"источник",
    r"статист",
    r"рынок",
    r"цена",
    r"стоимост",
    r"сколько стоит",
    r"курс",
    r"проверь",
    r"фактчек",
    r"факт[- ]?чекинг",
    r"релиз",
    r"анонс",
    r"дат[а-я]* выход",
    r"выйд",
]

SEARCH_RE = re.compile("|".join(SEARCH_PATTERNS), re.IGNORECASE)


def needs_web_search(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(SEARCH_RE.search(normalized))
