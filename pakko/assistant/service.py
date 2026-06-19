import asyncio
import logging
import re
import time
from datetime import UTC, datetime

from pakko.config import Settings
from pakko.llm.client import LLMResult, OpenAIResponsesClient
from pakko.llm.prompts import SYSTEM_PROMPT
from pakko.memory.repository import MessageRecord
from pakko.memory.service import MemoryService
from pakko.search import needs_web_search
from pakko.summarization.service import SummarizationService

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bнизк(?:ая|ой|ую)\s+уверенност",
        r"\bне\s+до\s+конца\s+увер",
        r"\bне\s+уверен",
        r"\bданных\s+недостаточно\b",
        r"\bнет\s+достоверн(?:ой|ых)\s+информац",
        r"\blow\s+confidence\b",
    )
)

WEB_SEARCH_RETRY_PROMPT = """Предыдущая попытка ответа получилась низкой уверенности.
Используй веб-поиск, чтобы проверить факты и усилить ответ, но не затягивай исследование.
Если после веб-поиска уверенность все еще низкая, дай лучший доступный ответ и прямо отметь это.
Не начинай с технических пояснений о повторной попытке."""


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
        result = await self._create_response_with_budget(
            messages,
            use_web_search=use_web_search,
            started_at=started_at,
        )
        web_search_retry = False

        if self._should_retry_with_web_search(result, use_web_search, started_at):
            try:
                result = await self._create_response_with_budget(
                    self._build_retry_messages(messages),
                    use_web_search=True,
                    started_at=started_at,
                )
                web_search_retry = True
            except TimeoutError:
                logger.warning("web_search_retry_timeout chat_id=%s", chat_id)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)

        response_text = result.text
        await self._memory.append_exchange(chat_id, user_text, response_text)
        await self._summarization.summarize_if_needed(chat_id)

        logger.info(
            (
                "assistant_response chat_id=%s web_search_requested=%s web_search_retry=%s "
                "web_search_used=%s low_confidence=%s sources=%s model=%s tokens_in=%s "
                "tokens_out=%s tokens_total=%s cost_usd=%.6f elapsed_ms=%s"
            ),
            chat_id,
            use_web_search,
            web_search_retry,
            result.web_search_used,
            is_low_confidence_answer(response_text),
            len(result.sources),
            result.model,
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.usage.total_tokens,
            result.usage.estimated_cost_usd,
            elapsed_ms,
        )
        return response_text[: self._settings.max_response_chars].strip()

    async def _create_response_with_budget(
        self,
        messages: list[dict[str, str]],
        *,
        use_web_search: bool,
        started_at: float,
    ) -> LLMResult:
        timeout = self._remaining_answer_seconds(started_at)
        if timeout <= 0:
            raise TimeoutError("Answer time budget exceeded")
        return await asyncio.wait_for(
            self._llm.create_response(messages, use_web_search=use_web_search),
            timeout=timeout,
        )

    def _should_retry_with_web_search(
        self,
        result: LLMResult,
        use_web_search: bool,
        started_at: float,
    ) -> bool:
        if not self._settings.enable_web_search or use_web_search:
            return False
        if not is_low_confidence_answer(result.text):
            return False
        return self._remaining_answer_seconds(started_at) > 1

    def _remaining_answer_seconds(self, started_at: float) -> float:
        return self._settings.max_answer_seconds - (time.perf_counter() - started_at)

    @staticmethod
    def _build_retry_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if not messages:
            return [{"role": "developer", "content": WEB_SEARCH_RETRY_PROMPT}]
        return [
            *messages[:-1],
            {"role": "developer", "content": WEB_SEARCH_RETRY_PROMPT},
            messages[-1],
        ]

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


def is_low_confidence_answer(text: str) -> bool:
    return any(pattern.search(text) for pattern in LOW_CONFIDENCE_PATTERNS)
