import re


def is_addressed_to_bot(text: str, username: str) -> bool:
    if not text:
        return False
    username_pattern = re.compile(rf"@{re.escape(username)}\b", re.IGNORECASE)
    name_pattern = re.compile(r"(?<![\w@])(pakko|пакко)(?!\w)", re.IGNORECASE)
    return bool(username_pattern.search(text) or name_pattern.search(text))


def strip_bot_addressing(text: str, username: str) -> str:
    without_username = re.sub(rf"@{re.escape(username)}\b", "", text, flags=re.IGNORECASE)
    without_name = re.sub(r"(?<![\w@])(pakko|пакко)(?!\w)", "", without_username, flags=re.IGNORECASE)
    cleaned = without_name.strip(" \t\r\n,.:;!?-")
    return cleaned or text.strip()
