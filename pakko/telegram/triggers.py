import re
from collections.abc import Iterable
from typing import Any

NAME_PATTERN = re.compile(r"(?<![\w@])(pakko|пакко)(?!\w)", re.IGNORECASE)


def normalize_bot_username(username: str) -> str:
    return username.strip().lstrip("@")


def _entity_type(entity: Any) -> str:
    entity_type = getattr(entity, "type", "")
    return getattr(entity_type, "value", entity_type)


def _extract_entity_text(text: str, entity: Any) -> str:
    extract_from = getattr(entity, "extract_from", None)
    if callable(extract_from):
        return extract_from(text)
    offset = getattr(entity, "offset", 0)
    return text[offset : offset + getattr(entity, "length", 0)]


def _is_mentioned_by_entity(text: str, username: str, entities: Iterable[Any] | None) -> bool:
    if not entities:
        return False

    mention = f"@{username}".casefold()
    for entity in entities:
        entity_type = _entity_type(entity)
        if entity_type == "mention" and _extract_entity_text(text, entity).casefold() == mention:
            return True

        if entity_type == "text_mention":
            user = getattr(entity, "user", None)
            entity_username = normalize_bot_username(getattr(user, "username", "") or "")
            if entity_username.casefold() == username.casefold():
                return True

    return False


def is_addressed_to_bot(
    text: str,
    username: str,
    entities: Iterable[Any] | None = None,
) -> bool:
    if not text:
        return False
    username = normalize_bot_username(username)
    username_pattern = re.compile(rf"@{re.escape(username)}\b", re.IGNORECASE)
    return bool(
        username_pattern.search(text)
        or NAME_PATTERN.search(text)
        or _is_mentioned_by_entity(text, username, entities)
    )


def strip_bot_addressing(text: str, username: str) -> str:
    username = normalize_bot_username(username)
    without_username = re.sub(rf"@{re.escape(username)}\b", "", text, flags=re.IGNORECASE)
    without_name = NAME_PATTERN.sub("", without_username)
    cleaned = without_name.strip(" \t\r\n,.:;!?-")
    return cleaned or text.strip()
