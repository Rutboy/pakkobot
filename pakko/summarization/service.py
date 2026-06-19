import logging

from pakko.config import Settings
from pakko.llm.client import OpenAIResponsesClient
from pakko.llm.prompts import SUMMARY_PROMPT
from pakko.memory.repository import SQLiteMemoryRepository

logger = logging.getLogger(__name__)


class SummarizationService:
    def __init__(
        self,
        settings: Settings,
        repository: SQLiteMemoryRepository,
        llm: OpenAIResponsesClient,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._llm = llm

    async def summarize_if_needed(self, chat_id: int) -> None:
        message_count = await self._repository.count_messages(chat_id)
        if message_count < self._settings.summarize_after_messages:
            return

        messages = await self._repository.list_messages(chat_id)
        transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
        result = await self._llm.summarize(
            [
                {"role": "developer", "content": SUMMARY_PROMPT},
                {"role": "user", "content": transcript},
            ]
        )
        await self._repository.replace_summary_and_prune(
            chat_id,
            result.text,
            self._settings.max_recent_messages,
        )
        logger.info(
            "context_summarized chat_id=%s messages=%s tokens=%s cost_usd=%.6f",
            chat_id,
            message_count,
            result.usage.total_tokens,
            result.usage.estimated_cost_usd,
        )
