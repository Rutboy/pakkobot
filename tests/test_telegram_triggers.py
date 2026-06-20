from aiogram.enums import MessageEntityType
from aiogram.types import MessageEntity

from pakko.telegram.triggers import is_addressed_to_bot, strip_bot_addressing


def test_group_trigger_by_username() -> None:
    assert is_addressed_to_bot("@pakkkobot найди статистику", "pakkkobot")


def test_group_trigger_by_username_from_env_with_at_sign() -> None:
    assert is_addressed_to_bot("@pakkkobot пожелай доброе утро на иврите", "@pakkkobot")


def test_group_trigger_by_telegram_mention_entity() -> None:
    text = "@pakkkobot пожелай доброе утро на иврите"
    entities = [
        MessageEntity(
            type=MessageEntityType.MENTION,
            offset=0,
            length=len("@pakkkobot"),
        )
    ]

    assert is_addressed_to_bot(text, "pakkkobot", entities)


def test_group_trigger_by_names_case_insensitive() -> None:
    assert is_addressed_to_bot("Пакко, проверь факт", "pakkkobot")
    assert is_addressed_to_bot("pakko расскажи подробнее", "pakkkobot")


def test_group_trigger_by_user_example_name() -> None:
    assert is_addressed_to_bot("Пакко, пожелай доброе утро на иврите", "pakkkobot")


def test_group_ignores_unaddressed_message() -> None:
    assert not is_addressed_to_bot("просто разговор в группе", "pakkkobot")


def test_strip_addressing() -> None:
    assert strip_bot_addressing("Пакко, проверь факт", "pakkkobot") == "проверь факт"
    assert strip_bot_addressing("@pakkkobot найди статистику", "pakkkobot") == "найди статистику"


def test_strip_user_examples() -> None:
    assert (
        strip_bot_addressing("Пакко, пожелай доброе утро на иврите", "pakkkobot")
        == "пожелай доброе утро на иврите"
    )
    assert (
        strip_bot_addressing("@pakkkobot пожелай доброе утро на иврите", "pakkkobot")
        == "пожелай доброе утро на иврите"
    )
