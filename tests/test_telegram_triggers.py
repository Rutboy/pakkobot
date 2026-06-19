from pakko.telegram.triggers import is_addressed_to_bot, strip_bot_addressing


def test_group_trigger_by_username() -> None:
    assert is_addressed_to_bot("@pakkkobot найди статистику", "pakkkobot")


def test_group_trigger_by_names_case_insensitive() -> None:
    assert is_addressed_to_bot("Пакко, проверь факт", "pakkkobot")
    assert is_addressed_to_bot("pakko расскажи подробнее", "pakkkobot")


def test_group_ignores_unaddressed_message() -> None:
    assert not is_addressed_to_bot("просто разговор в группе", "pakkkobot")


def test_strip_addressing() -> None:
    assert strip_bot_addressing("Пакко, проверь факт", "pakkkobot") == "проверь факт"
    assert strip_bot_addressing("@pakkkobot найди статистику", "pakkkobot") == "найди статистику"
