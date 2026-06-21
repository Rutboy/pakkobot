import logging
import re
from base64 import b64encode
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from openai import AsyncOpenAI

from pakko.config import Settings

logger = logging.getLogger(__name__)

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "igshid", "ref"}
MAX_INLINE_CITATIONS = 5
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)]\((https?://[^\s)]+)\)")


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
    web_search_used: bool = False


@dataclass(frozen=True, slots=True)
class LLMInputAttachment:
    filename: str
    mime_type: str
    data: bytes

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    def to_content_item(self) -> dict[str, str]:
        encoded = b64encode(self.data).decode("ascii")
        data_url = f"data:{self.mime_type};base64,{encoded}"
        if self.is_image:
            return {"type": "input_image", "image_url": data_url}
        return {
            "type": "input_file",
            "filename": self.filename,
            "file_data": data_url,
        }


class OpenAIResponsesClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def create_response(
        self,
        messages: list[dict[str, Any]],
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
            params["tool_choice"] = "required"

        response = await self._client.responses.create(**params)
        text = self._extract_text(response)
        usage = self._extract_usage(response)
        sources = self._extract_sources(response)
        model = str(getattr(response, "model", self._settings.openai_model))
        return LLMResult(
            text=text,
            usage=usage,
            model=model,
            sources=sources,
            web_search_used=self._has_web_search_call(response),
        )

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
            web_search_used=False,
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
        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if not text:
                    continue
                chunks.append(
                    OpenAIResponsesClient._apply_inline_citations(
                        str(text),
                        list(getattr(content, "annotations", []) or []),
                    )
                )
        if chunks:
            return "\n".join(chunks).strip()

        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text).strip()
        return ""

    @staticmethod
    def _apply_inline_citations(text: str, annotations: list[Any]) -> str:
        citations = [annotation for annotation in annotations if getattr(annotation, "url", None)]
        if not citations:
            return text

        selected = citations[:MAX_INLINE_CITATIONS]
        selected_ids = {id(annotation) for annotation in selected}
        parts: list[str] = []
        cursor = 0
        for annotation in citations:
            start = int(getattr(annotation, "start_index", -1))
            end = int(getattr(annotation, "end_index", -1))
            url = normalize_source_url(str(getattr(annotation, "url", "")))
            if not url or start < cursor or end <= start or end > len(text):
                continue
            parts.append(text[cursor:start])
            label = text[start:end]
            if id(annotation) in selected_ids:
                parts.append(f"[{citation_label(label)}]({url})")
            else:
                parts.append(label)
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts)

    @staticmethod
    def _extract_sources(response: Any) -> list[str]:
        sources: list[str] = []
        seen: set[str] = set()
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                for annotation in getattr(content, "annotations", []) or []:
                    OpenAIResponsesClient._append_source(sources, seen, annotation)
        return sources[:MAX_INLINE_CITATIONS]

    @staticmethod
    def _append_source(sources: list[str], seen: set[str], source: Any) -> None:
        url = normalize_source_url(str(getattr(source, "url", "") or ""))
        title = str(getattr(source, "title", "") or url)
        if not url or url in seen:
            return
        seen.add(url)
        sources.append(f"{title}: {url}")

    @staticmethod
    def _has_web_search_call(response: Any) -> bool:
        return any(
            getattr(item, "type", None) == "web_search_call"
            for item in getattr(response, "output", []) or []
        )


def normalize_source_url(url: str) -> str:
    if not url:
        return ""
    split = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if key not in TRACKING_QUERY_KEYS
            and not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
        ],
        doseq=True,
    )
    return urlunsplit((split.scheme, split.netloc, split.path, query, ""))


def citation_label(label: str) -> str:
    markdown_link = MARKDOWN_LINK_RE.search(label)
    if markdown_link:
        return markdown_link.group(1).strip()
    return label.strip(" ()[]") or "Источник"
