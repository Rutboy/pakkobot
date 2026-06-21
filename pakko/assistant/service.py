import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from pakko.assistant.confidence import ConfidenceAssessment, assess_confidence
from pakko.config import Settings
from pakko.llm.client import LLMInputAttachment, LLMResult, OpenAIResponsesClient
from pakko.llm.prompts import SYSTEM_PROMPT
from pakko.memory.repository import MessageRecord
from pakko.memory.service import MemoryService
from pakko.search import needs_web_search
from pakko.summarization.service import SummarizationService

logger = logging.getLogger(__name__)

WEB_SEARCH_RETRY_PROMPT = """Предыдущая попытка ответа получилась низкой уверенности
или попросила веб-проверку через технический маркер.
Используй веб-поиск, чтобы проверить факты и усилить ответ, но не затягивай исследование.
Если после веб-поиска уверенность все еще низкая, дай лучший доступный ответ
и отметь это только в техническом маркере.
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

    async def answer(
        self,
        chat_id: int,
        user_text: str,
        reply_context: str | None = None,
        attachments: list[LLMInputAttachment] | None = None,
    ) -> str:
        if self._memory.is_clear_intent(user_text):
            await self._memory.clear_chat(chat_id)
            return "Контекст очищен. Начинаем новый диалог."

        loaded_context = await self._memory.load_context_with_status(chat_id)
        context = loaded_context.context
        input_attachments = attachments or []
        current_user_prompt = self._build_current_user_prompt(user_text, reply_context)
        use_web_search = self._settings.enable_web_search and needs_web_search(current_user_prompt)
        messages = self._build_messages(
            current_user_prompt,
            context.summary,
            context.messages,
            attachments=input_attachments,
        )

        started_at = time.perf_counter()
        web_search_retry = False
        timed_out = False
        result = await self._llm.create_response(messages, use_web_search=use_web_search)
        assessment = self._apply_confidence_assessment(result)

        if self._should_retry_with_web_search(assessment, use_web_search, started_at):
            try:
                result = await self._create_response_with_improvement_budget(
                    self._build_retry_messages(messages),
                    use_web_search=True,
                    started_at=started_at,
                )
                assessment = self._apply_confidence_assessment(result)
                web_search_retry = True
            except TimeoutError:
                timed_out = True
                logger.warning("web_search_retry_timeout chat_id=%s", chat_id)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)

        response_text = result.text
        await self._memory.append_exchange(
            chat_id,
            self._memory_user_text(user_text, input_attachments),
            response_text,
        )
        await self._summarization.summarize_if_needed(chat_id)

        logger.info(
            (
                "assistant_response chat_id=%s web_search_requested=%s web_search_retry=%s "
                "web_search_used=%s confidence_level=%s source_reliability=%s "
                "web_needed=%s confidence_marker_found=%s timed_out=%s sources=%s model=%s "
                "tokens_in=%s tokens_out=%s tokens_total=%s cost_usd=%.6f elapsed_ms=%s "
                "context_reset_due_to_inactivity=%s attachments=%s"
            ),
            chat_id,
            use_web_search,
            web_search_retry,
            result.web_search_used,
            assessment.level,
            assessment.source,
            assessment.web_needed,
            assessment.marker_found,
            timed_out,
            len(result.sources),
            result.model,
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.usage.total_tokens,
            result.usage.estimated_cost_usd,
            elapsed_ms,
            loaded_context.reset_due_to_inactivity,
            len(input_attachments),
        )
        return response_text[: self._settings.max_response_chars].strip()

    async def _create_response_with_improvement_budget(
        self,
        messages: list[dict[str, Any]],
        *,
        use_web_search: bool,
        started_at: float,
    ) -> LLMResult:
        timeout = self._remaining_answer_seconds(started_at)
        if timeout <= 0:
            raise TimeoutError("Answer improvement budget exceeded")
        return await asyncio.wait_for(
            self._llm.create_response(messages, use_web_search=use_web_search),
            timeout=timeout,
        )

    def _should_retry_with_web_search(
        self,
        assessment: ConfidenceAssessment,
        use_web_search: bool,
        started_at: float,
    ) -> bool:
        if not self._settings.enable_web_search or use_web_search:
            return False
        if not assessment.should_improve_with_web_search:
            return False
        return self._remaining_answer_seconds(started_at) > 1

    def _remaining_answer_seconds(self, started_at: float) -> float:
        return self._settings.max_answer_seconds - (time.perf_counter() - started_at)

    @staticmethod
    def _apply_confidence_assessment(result: LLMResult) -> ConfidenceAssessment:
        assessment = assess_confidence(result.text)
        result.text = assessment.clean_text
        return assessment

    @staticmethod
    def _build_current_user_prompt(user_text: str, reply_context: str | None) -> str:
        if not reply_context:
            return user_text
        return (
            "Context from the Telegram message this request replies to:\n"
            f"{reply_context.strip()}\n\n"
            "Current user request:\n"
            f"{user_text}"
        )

    @staticmethod
    def _build_retry_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        *,
        attachments: list[LLMInputAttachment] | None = None,
    ) -> list[dict[str, Any]]:
        today = datetime.now(UTC).date().isoformat()
        messages: list[dict[str, Any]] = [
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
        messages.append({
            "role": "user",
            "content": self._build_user_content(user_text, attachments or []),
        })
        return messages

    @staticmethod
    def _build_user_content(
        user_text: str,
        attachments: list[LLMInputAttachment],
    ) -> str | list[dict[str, str]]:
        if not attachments:
            return user_text
        return [
            {"type": "input_text", "text": user_text},
            *(attachment.to_content_item() for attachment in attachments),
        ]

    @staticmethod
    def _memory_user_text(user_text: str, attachments: list[LLMInputAttachment]) -> str:
        if not attachments:
            return user_text
        names = ", ".join(attachment.filename for attachment in attachments)
        return f"{user_text}\n\n[Attachments: {names}]"

