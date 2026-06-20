import logging
from datetime import UTC, datetime
from typing import cast

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, ReplyParameters
from aiogram.utils.chat_action import ChatActionSender

from pakko.assistant import AssistantService
from pakko.config import Settings
from pakko.memory.repository import SQLiteMemoryRepository
from pakko.search import needs_web_search
from pakko.telegram.formatting import split_markdown_as_telegram_html
from pakko.telegram.triggers import (
    is_addressed_to_bot,
    normalize_bot_username,
    strip_bot_addressing,
)

logger = logging.getLogger(__name__)

IGNORED_TELEGRAM_USER_IDS = frozenset({6260255228})

START_TEXT = """Пакко помогает искать информацию, проверять факты и собирать краткие исследования.

Что можно спросить:
- проверь факт и покажи, где могут быть сомнения;
- найди свежие данные с источниками;
- сравни варианты и выдели главное;
- объясни сложную тему простыми словами.

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
Пакко, сравни эти два подхода
Пакко, объясни проще

Я лучше всего работаю с текстовыми вопросами.
Вложения пока не анализирую: если важна картинка, файл или голосовое, опишите его текстом.
"""

UNSUPPORTED_MESSAGE_TEXT = (
    "Пока понимаю только текстовые сообщения. "
    "Пришлите вопрос текстом, а если вложение важно, кратко опишите его."
)

SEARCH_STATUS_TEXT = "Ищу и проверяю источники..."


def _is_not_ignored_user(message: Message) -> bool:
    user = message.from_user
    if not user:
        return True

    return user.id not in IGNORED_TELEGRAM_USER_IDS


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


def _format_last_activity(value: datetime | None) -> str:
    if value is None:
        return "нет"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    seconds = int((datetime.now(UTC) - value).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "только что"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} {_plural_ru(minutes, 'минуту', 'минуты', 'минут')} назад"

    hours = minutes // 60
    if hours < 24:
        return f"{hours} {_plural_ru(hours, 'час', 'часа', 'часов')} назад"

    days = hours // 24
    return f"{days} {_plural_ru(days, 'день', 'дня', 'дней')} назад"


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    if 11 <= value % 100 <= 14:
        return many
    if value % 10 == 1:
        return one
    if 2 <= value % 10 <= 4:
        return few
    return many


def _should_show_search_status(
    settings: Settings,
    user_text: str,
    reply_context: str | None,
) -> bool:
    if not settings.enable_web_search:
        return False
    probe_text = AssistantService._build_current_user_prompt(user_text, reply_context)
    return needs_web_search(probe_text)


async def _delete_message_safely(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.debug("failed_to_delete_status_message", exc_info=True)


def build_router(
    settings: Settings,
    assistant: AssistantService,
    repository: SQLiteMemoryRepository,
) -> Router:
    router = Router()
    router.message.filter(_is_not_ignored_user)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(START_TEXT)

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("clear"))
    async def clear(message: Message) -> None:
        await repository.clear_chat(message.chat.id)
        await message.answer("Контекст очищен. Начинаем новый диалог.")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        chat_status = await repository.status(message.chat.id)
        last_activity = _format_last_activity(chat_status.last_activity_at)
        await message.answer(
            "\n".join(
                [
                    "Статус контекста:",
                    f"- сообщений в памяти: {chat_status.message_count}",
                    f"- размер summary: {chat_status.summary_chars} символов",
                    f"- последняя активность: {last_activity}",
                    "\nЧтобы начать с чистого листа, отправьте /clear.",
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

        reply_context = _reply_context_text(message)
        status_message: Message | None = None
        if _should_show_search_status(settings, user_text, reply_context):
            status_message = await message.answer(
                SEARCH_STATUS_TEXT,
                reply_parameters=reply_parameters,
            )

        logger.info("user_request chat_id=%s text_length=%s", message.chat.id, len(user_text))
        try:
            bot = cast(Bot, message.bot)
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                answer = await assistant.answer(
                    message.chat.id,
                    user_text,
                    reply_context=reply_context,
                )
            await _delete_message_safely(status_message)
            for chunk in split_markdown_as_telegram_html(answer):
                await message.answer(
                    chunk,
                    parse_mode=ParseMode.HTML,
                    reply_parameters=reply_parameters,
                )
        except Exception:
            await _delete_message_safely(status_message)
            logger.exception("failed_to_handle_message chat_id=%s", message.chat.id)
            await message.answer(
                "Не удалось обработать запрос. Попробуйте еще раз позже.",
                reply_parameters=reply_parameters,
            )

    @router.message()
    async def unsupported_message(message: Message) -> None:
        caption = (message.caption or "").strip()
        if message.chat.type != "private" and not (
            is_addressed_to_bot(
                caption,
                settings.telegram_bot_username,
                message.caption_entities,
            )
            or _is_reply_to_bot(message, settings.telegram_bot_username)
        ):
            return

        await message.answer(
            UNSUPPORTED_MESSAGE_TEXT,
            reply_parameters=_reply_parameters_for_group(message),
        )

    return router
