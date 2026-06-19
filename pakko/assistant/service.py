import logging
import time
from datetime import UTC, datetime

from pakko.config import Settings
from pakko.llm.client import OpenAIResponsesClient
from pakko.llm.prompts import SYSTEM_PROMPT
from pakko.memory.repository import MessageRecord
from pakko.memory.service import MemoryService
from pakko.search import needs_web_search
from pakko.summarization.service import SummarizationService

logger = logging.getLogger(__name__)


class AssistantService:
    def __init__(
        self,
        settings: Settings,
        memory: MemoryService,
        llm: OpenAIResponsesClient,
        summarization: SummarizationService,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._llm = llm
        self._summarization = summarization

    async def answer(self, chat_id: int, user_text: str) -> str:
        if self._memory.is_clear_intent(user_text):
            await self._memory.clear_chat(chat_id)
            return "Контекст очищен. Начинаем новый диалог."

        context = await self._memory.load_context(chat_id)
        use_web_search = self._settings.enable_web_search and needs_web_search(user_text)
        messages = self._build_messages(user_text, context.summary, context.messages)

        started_at = time.perf_counter()
        result = await self._llm.create_response(messages, use_web_search=use_web_search)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)

        await self._memory.append_exchange(chat_id, user_text, result.text)
        await self._summarization.summarize_if_needed(chat_id)

        logger.info(
            (
                "assistant_response chat_id=%s web_search=%s model=%s "
                "tokens_in=%s tokens_out=%s tokens_total=%s cost_usd=%.6f elapsed_ms=%s"
            ),
            chat_id,
            use_web_search,
            result.model,
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.usage.total_tokens,
            result.usage.estimated_cost_usd,
            elapsed_ms,
        )
        return result.text[: self._settings.max_response_chars].strip()

    def _build_messages(
        self,
        user_text: str,
        summary: str | None,
        recent_messages: list[MessageRecord],
    ) -> list[dict[str, str]]:
        today = datetime.now(UTC).date().isoformat()
        messages: list[dict[str, str]] = [
            {
                "role": "developer",
                "content": f"{SYSTEM_PROMPT}\nТекущая дата UTC: {today}.",
            }
        ]
        if summary:
            messages.append(
                {
                    "role": "developer",
                    "content": f"Краткий контекст предыдущего диалога:\n{summary}",
                }
            )
        for message in recent_messages:
            messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": user_text})
        return messages


