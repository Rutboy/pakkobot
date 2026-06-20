import logging
from typing import cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, ReplyParameters
from aiogram.utils.chat_action import ChatActionSender

from pakko.assistant import AssistantService
from pakko.config import Settings
from pakko.memory.repository import SQLiteMemoryRepository
from pakko.telegram.formatting import split_markdown_as_telegram_html
from pakko.telegram.triggers import (
    is_addressed_to_bot,
    normalize_bot_username,
    strip_bot_addressing,
)

logger = logging.getLogger(__name__)

START_TEXT = """Пакко помогает искать информацию, проверять факты и собирать краткие исследования.

В личном чате просто отправьте вопрос. В группе обратитесь ко мне через @username, Pakko или Пакко.
"""

HELP_TEXT = """Команды:
/start - описание возможностей
/help - справка
/clear - очистить контекст текущего чата
/status - состояние памяти текущего чата

Примеры:
Пакко, проверь этот факт
@pakkkobot найди свежую статистику рынка игр
pakko расскажи подробнее
"""


def _is_reply_to_bot(message: Message, username: str) -> bool:
    reply = message.reply_to_message
    if not reply or not reply.from_user:
        return False

    bot_id = getattr(message.bot, "id", None)
    if bot_id is not None and reply.from_user.id == bot_id:
        return True

    reply_username = reply.from_user.username
    if not reply_username:
        return False

    return (
        normalize_bot_username(reply_username).casefold()
        == normalize_bot_username(username).casefold()
    )


def _reply_parameters_for_group(message: Message) -> ReplyParameters | None:
    if message.chat.type == "private":
        return None

    return ReplyParameters(message_id=message.message_id)


def _reply_context_text(message: Message) -> str | None:
    reply = message.reply_to_message
    if not reply:
        return None

    text = getattr(reply, "text", None) or getattr(reply, "caption", None)
    if not text:
        return None

    return text.strip() or None


def build_router(
    settings: Settings,
    assistant: AssistantService,
    repository: SQLiteMemoryRepository,
) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(START_TEXT)

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("clear"))
    async def clear(message: Message) -> None:
        await repository.clear_chat(message.chat.id)
        await message.answer("Контекст очищен.")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        chat_status = await repository.status(message.chat.id)
        last_activity = (
            chat_status.last_activity_at.isoformat() if chat_status.last_activity_at else "нет"
        )
        await message.answer(
            "\n".join(
                [
                    "Статус контекста:",
                    f"- сообщений в памяти: {chat_status.message_count}",
                    f"- размер summary: {chat_status.summary_chars} символов",
                    f"- последняя активность: {last_activity}",
                ]
            )
        )

    @router.message(F.text)
    async def text_message(message: Message) -> None:
        text = message.text or ""
        if message.chat.type != "private" and not (
            is_addressed_to_bot(text, settings.telegram_bot_username, message.entities)
            or _is_reply_to_bot(message, settings.telegram_bot_username)
        ):
            return

        user_text = strip_bot_addressing(text, settings.telegram_bot_username)
        reply_parameters = _reply_parameters_for_group(message)
        if not user_text:
            await message.answer(
                "Слушаю. Задайте вопрос.",
                reply_parameters=reply_parameters,
            )
            return

        logger.info("user_request chat_id=%s text_length=%s", message.chat.id, len(user_text))
        try:
            bot = cast(Bot, message.bot)
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                answer = await assistant.answer(
                    message.chat.id,
                    user_text,
                    reply_context=_reply_context_text(message),
                )
            for chunk in split_markdown_as_telegram_html(answer):
                await message.answer(
                    chunk,
                    parse_mode=ParseMode.HTML,
                    reply_parameters=reply_parameters,
                )
        except Exception:
            logger.exception("failed_to_handle_message chat_id=%s", message.chat.id)
            await message.answer(
                "Не удалось обработать запрос. Попробуйте еще раз позже.",
                reply_parameters=reply_parameters,
            )

    return router
