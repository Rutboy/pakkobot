from dataclasses import dataclass
from datetime import UTC, datetime

from pakko.config import Settings
from pakko.memory.repository import ChatContext, SQLiteMemoryRepository


@dataclass(slots=True)
class LoadedContext:
    context: ChatContext
    reset_due_to_inactivity: bool = False


class MemoryService:
    def __init__(self, settings: Settings, repository: SQLiteMemoryRepository) -> None:
        self._settings = settings
        self._repository = repository

    async def load_context(self, chat_id: int) -> ChatContext:
        return (await self.load_context_with_status(chat_id)).context

    async def load_context_with_status(self, chat_id: int) -> LoadedContext:
        context = await self._repository.get_context(chat_id, self._settings.max_recent_messages)
        age_seconds = (datetime.now(UTC) - context.last_activity_at).total_seconds()
        if age_seconds >= self._settings.context_ttl_seconds:
            await self._repository.clear_chat(chat_id)
            return LoadedContext(
                context=await self._repository.get_context(
                    chat_id,
                    self._settings.max_recent_messages,
                ),
                reset_due_to_inactivity=True,
            )
        return LoadedContext(context=context)

    async def append_exchange(self, chat_id: int, user_text: str, assistant_text: str) -> None:
        await self._repository.append_message(chat_id, "user", user_text)
        await self._repository.append_message(chat_id, "assistant", assistant_text)

    async def clear_chat(self, chat_id: int) -> None:
        await self._repository.clear_chat(chat_id)

    @staticmethod
    def is_clear_intent(text: str) -> bool:
        normalized = text.strip().lower()
        clear_phrases = {
            "очисти память",
            "очистить память",
            "сбрось контекст",
            "сбросить контекст",
            "новый диалог",
            "начать заново",
            "clear memory",
            "reset context",
            "new chat",
            "new conversation",
        }
        return normalized in clear_phrases
