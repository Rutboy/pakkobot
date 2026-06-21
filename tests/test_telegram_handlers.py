from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pakko.telegram.handlers import (
    _attachment_too_large,
    _format_last_activity,
    _has_supported_input,
    _is_not_ignored_user,
    _is_reply_to_bot,
    _message_text,
    _reply_context_text,
    _reply_parameters_for_group,
)


def make_message(
    *,
    bot_id: int | None,
    reply_user_id: int,
    reply_username: str | None = None,
    chat_type: str = "group",
    message_id: int = 123,
):
    return SimpleNamespace(
        bot=SimpleNamespace(id=bot_id),
        chat=SimpleNamespace(type=chat_type),
        message_id=message_id,
        reply_to_message=SimpleNamespace(
            from_user=SimpleNamespace(id=reply_user_id, username=reply_username),
            text="original message",
            caption=None,
        ),
    )


def test_group_reply_to_bot_by_id_is_addressed() -> None:
    message = make_message(bot_id=42, reply_user_id=42, reply_username="someone_else")

    assert _is_reply_to_bot(message, "pakkkobot")


def test_group_reply_to_bot_by_username_is_addressed_when_bot_id_is_unavailable() -> None:
    message = make_message(bot_id=None, reply_user_id=42, reply_username="PakKKoBot")

    assert _is_reply_to_bot(message, "@pakkkobot")


def test_group_reply_to_other_user_is_not_addressed() -> None:
    message = make_message(bot_id=42, reply_user_id=100, reply_username="someone_else")

    assert not _is_reply_to_bot(message, "pakkkobot")


def test_group_answer_uses_original_message_as_reply_target() -> None:
    message = make_message(bot_id=42, reply_user_id=100, chat_type="group", message_id=321)

    reply_parameters = _reply_parameters_for_group(message)

    assert reply_parameters is not None
    assert reply_parameters.message_id == 321


def test_private_answer_does_not_force_reply() -> None:
    message = make_message(bot_id=42, reply_user_id=100, chat_type="private", message_id=321)

    assert _reply_parameters_for_group(message) is None


def test_reply_context_uses_replied_text() -> None:
    message = make_message(bot_id=42, reply_user_id=100)

    assert _reply_context_text(message) == "original message"


def test_reply_context_falls_back_to_caption() -> None:
    message = make_message(bot_id=42, reply_user_id=100)
    message.reply_to_message.text = None
    message.reply_to_message.caption = "caption text"

    assert _reply_context_text(message) == "caption text"


def test_reply_context_ignores_blank_text() -> None:
    message = make_message(bot_id=42, reply_user_id=100)
    message.reply_to_message.text = "   "

    assert _reply_context_text(message) is None


def test_ignored_user_is_filtered_out() -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=6260255228, is_bot=False))

    assert not _is_not_ignored_user(message)


def test_bot_user_is_filtered_out() -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=100, is_bot=True))

    assert not _is_not_ignored_user(message)


def test_other_user_is_not_filtered_out() -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=100, is_bot=False))

    assert _is_not_ignored_user(message)


def test_message_without_user_is_not_filtered_out() -> None:
    message = SimpleNamespace(from_user=None)

    assert _is_not_ignored_user(message)


def test_format_last_activity_uses_human_readable_relative_time() -> None:
    value = datetime.now(UTC) - timedelta(minutes=5)

    assert _format_last_activity(value) == "5 минут назад"


def test_message_text_uses_caption_when_text_is_missing() -> None:
    message = SimpleNamespace(text=None, caption="  caption question  ")

    assert _message_text(message) == "caption question"


def test_supported_input_accepts_photo_without_text() -> None:
    message = SimpleNamespace(text=None, caption=None, photo=[object()], document=None)

    assert _has_supported_input(message)


def test_attachment_too_large_uses_configured_limit() -> None:
    settings = SimpleNamespace(max_input_file_bytes=10)

    assert _attachment_too_large(11, settings)
    assert not _attachment_too_large(10, settings)
    assert not _attachment_too_large(None, settings)
