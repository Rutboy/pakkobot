import logging
import mimetypes
from datetime import UTC, datetime
from io import BytesIO
from typing import cast

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, ReplyParameters
from aiogram.utils.chat_action import ChatActionSender

from pakko.assistant import AssistantService
from pakko.config import Settings
from pakko.llm.client import LLMInputAttachment
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
DEFAULT_ATTACHMENT_PROMPT = "Проанализируй вложение и ответь на основе его содержимого."


def _is_not_ignored_user(message: Message) -> bool:
    user = message.from_user
    if not user:
        return True

    if getattr(user, "is_bot", False):
        return False

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


def _message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def _message_entities(message: Message) -> object:
    if message.text is not None:
        return message.entities
    return message.caption_entities


def _has_supported_input(message: Message) -> bool:
    return bool(message.text or message.caption or message.photo or message.document)


def _attachment_too_large(file_size: int | None, settings: Settings) -> bool:
    return file_size is not None and file_size > settings.max_input_file_bytes


async def _download_file_bytes(bot: Bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    if not telegram_file.file_path:
        raise ValueError("Telegram file_path is empty")

    buffer = BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)
    return buffer.getvalue()


async def _collect_input_attachments(
    message: Message,
    settings: Settings,
) -> tuple[list[LLMInputAttachment], list[str]]:
    attachments: list[LLMInputAttachment] = []
    rejected: list[str] = []
    bot = cast(Bot, message.bot)

    photos = list(message.photo or [])
    if photos:
        photo = max(photos, key=lambda item: ((item.file_size or 0), item.width * item.height))
        if _attachment_too_large(photo.file_size, settings):
            rejected.append("image")
        else:
            data = await _download_file_bytes(bot, photo.file_id)
            if len(data) > settings.max_input_file_bytes:
                rejected.append("image")
            else:
                attachments.append(
                    LLMInputAttachment(
                        filename=f"telegram-photo-{photo.file_unique_id}.jpg",
                        mime_type="image/jpeg",
                        data=data,
                    )
                )

    document = message.document
    if document:
        filename = document.file_name or f"telegram-file-{document.file_unique_id}"
        mime_type = (
            document.mime_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        if _attachment_too_large(document.file_size, settings):
            rejected.append(filename)
        else:
            data = await _download_file_bytes(bot, document.file_id)
            if len(data) > settings.max_input_file_bytes:
                rejected.append(filename)
            else:
                attachments.append(
                    LLMInputAttachment(
                        filename=filename,
                        mime_type=mime_type,
                        data=data,
                    )
                )

    return attachments, rejected


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


async def _answer_chunk_safely(
    message: Message,
    chunk: str,
    reply_parameters: ReplyParameters | None,
) -> None:
    try:
        await message.answer(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_parameters=reply_parameters,
        )
    except TelegramBadRequest:
        logger.warning("failed_to_send_html_answer", exc_info=True)
        await message.answer(chunk, reply_parameters=reply_parameters)


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

    @router.message(_has_supported_input)
    async def supported_message(message: Message) -> None:
        text = _message_text(message)
        if message.chat.type != "private" and not (
            is_addressed_to_bot(
                text,
                settings.telegram_bot_username,
                _message_entities(message),
            )
            or _is_reply_to_bot(message, settings.telegram_bot_username)
        ):
            return

        user_text = strip_bot_addressing(text, settings.telegram_bot_username).strip()
        reply_parameters = _reply_parameters_for_group(message)
        try:
            attachments, rejected_attachments = await _collect_input_attachments(message, settings)
        except Exception:
            logger.exception("failed_to_download_attachment chat_id=%s", message.chat.id)
            await message.answer(
                "Не удалось скачать вложение из Telegram. Попробуйте отправить его еще раз.",
                reply_parameters=reply_parameters,
            )
            return

        if rejected_attachments and not attachments:
            await message.answer(
                (
                    "Вложение слишком большое. "
                    f"Лимит: {settings.max_input_file_bytes // 1_000_000} МБ."
                ),
                reply_parameters=reply_parameters,
            )
            return

        if rejected_attachments:
            await message.answer(
                (
                    "Часть вложений пропущена из-за размера. "
                    f"Лимит: {settings.max_input_file_bytes // 1_000_000} МБ."
                ),
                reply_parameters=reply_parameters,
            )

        if not user_text and attachments:
            user_text = DEFAULT_ATTACHMENT_PROMPT

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

        logger.info(
            "user_request chat_id=%s text_length=%s attachments=%s",
            message.chat.id,
            len(user_text),
            len(attachments),
        )
        try:
            bot = cast(Bot, message.bot)
            async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                answer = await assistant.answer(
                    message.chat.id,
                    user_text,
                    reply_context=reply_context,
                    attachments=attachments,
                )
            await _delete_message_safely(status_message)
            for chunk in split_markdown_as_telegram_html(answer):
                await _answer_chunk_safely(message, chunk, reply_parameters)
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
