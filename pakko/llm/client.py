import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from pakko.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class LLMResult:
    text: str
    usage: LLMUsage
    model: str
    sources: list[str]


class OpenAIResponsesClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def create_response(
        self,
        messages: list[dict[str, str]],
        *,
        use_web_search: bool,
    ) -> LLMResult:
        params: dict[str, Any] = {
            "model": self._settings.openai_model,
            "input": messages,
        }
        if self._settings.openai_reasoning_effort != "none":
            params["reasoning"] = {"effort": self._settings.openai_reasoning_effort}
        if use_web_search:
            params["tools"] = [
                {
                    "type": "web_search",
                    "search_context_size": self._settings.web_search_context_size,
                }
            ]

        response = await self._client.responses.create(**params)
        text = self._extract_text(response)
        usage = self._extract_usage(response)
        sources = self._extract_sources(response)
        model = str(getattr(response, "model", self._settings.openai_model))
        return LLMResult(text=text, usage=usage, model=model, sources=sources)

    async def summarize(self, messages: list[dict[str, str]]) -> LLMResult:
        params: dict[str, Any] = {
            "model": self._settings.openai_model,
            "input": messages,
        }
        if self._settings.openai_reasoning_effort != "none":
            params["reasoning"] = {"effort": "low"}

        response = await self._client.responses.create(**params)
        return LLMResult(
            text=self._extract_text(response),
            usage=self._extract_usage(response),
            model=str(getattr(response, "model", self._settings.openai_model)),
            sources=[],
        )

    def _extract_usage(self, response: Any) -> LLMUsage:
        raw_usage = getattr(response, "usage", None)
        input_tokens = int(getattr(raw_usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(raw_usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(raw_usage, "total_tokens", input_tokens + output_tokens) or 0)
        cost = (
            input_tokens * self._settings.openai_input_price_usd_per_million
            + output_tokens * self._settings.openai_output_price_usd_per_million
        ) / 1_000_000
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text).strip()

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks).strip()

    @staticmethod
    def _extract_sources(response: Any) -> list[str]:
        sources: list[str] = []
        seen: set[str] = set()
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                for annotation in getattr(content, "annotations", []) or []:
                    url = getattr(annotation, "url", None)
                    title = getattr(annotation, "title", None)
                    if not url or url in seen:
                        continue
                    seen.add(str(url))
                    sources.append(f"{title or url}: {url}")
        return sources
