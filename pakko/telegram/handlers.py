import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from pakko.assistant import AssistantService
from pakko.config import Settings
from pakko.memory.repository import SQLiteMemoryRepository
from pakko.telegram.formatting import split_for_telegram
from pakko.telegram.triggers import is_addressed_to_bot, strip_bot_addressing

logger = logging.getLogger(__name__)

START_TEXT = """Pakko помогает искать информацию, проверять факты и собирать краткие исследования.

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
        if message.chat.type != "private" and not is_addressed_to_bot(
            text,
            settings.telegram_bot_username,
        ):
            return

        user_text = strip_bot_addressing(text, settings.telegram_bot_username)
        if not user_text:
            await message.answer("Слушаю. Задайте вопрос.")
            return

        logger.info("user_request chat_id=%s text_length=%s", message.chat.id, len(user_text))
        try:
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                answer = await assistant.answer(message.chat.id, user_text)
            for chunk in split_for_telegram(answer):
                await message.answer(chunk)
        except Exception:
            logger.exception("failed_to_handle_message chat_id=%s", message.chat.id)
            await message.answer("Не удалось обработать запрос. Попробуйте еще раз позже.")

    return router
