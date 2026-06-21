import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from pakko.assistant.service import AssistantService
from pakko.llm.client import LLMResult, LLMUsage
from pakko.memory.repository import ChatContext
from pakko.memory.service import LoadedContext


class FakeMemory:
    def __init__(self) -> None:
        self.exchanges: list[tuple[int, str, str]] = []
        self.cleared_chat_id: int | None = None
        self.reset_due_to_inactivity = False

    @staticmethod
    def is_clear_intent(text: str) -> bool:
        return text == "clear"

    async def clear_chat(self, chat_id: int) -> None:
        self.cleared_chat_id = chat_id

    async def load_context(self, chat_id: int) -> ChatContext:
        return ChatContext(
            chat_id=chat_id,
            summary=None,
            last_activity_at=datetime.now(UTC),
            messages=[],
        )

    async def load_context_with_status(self, chat_id: int) -> LoadedContext:
        return LoadedContext(
            context=await self.load_context(chat_id),
            reset_due_to_inactivity=self.reset_due_to_inactivity,
        )

    async def append_exchange(self, chat_id: int, user_text: str, assistant_text: str) -> None:
        self.exchanges.append((chat_id, user_text, assistant_text))


class FakeLLM:
    def __init__(self, results: list[LLMResult | BaseException], delay_seconds: float = 0) -> None:
        self.results = results
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[list[dict[str, str]], bool]] = []

    async def create_response(
        self,
        messages: list[dict[str, str]],
        *,
        use_web_search: bool,
    ) -> LLMResult:
        self.calls.append((messages, use_web_search))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeSummarization:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def summarize_if_needed(self, chat_id: int) -> None:
        self.calls.append(chat_id)


def make_settings(
    *,
    enable_web_search: bool = True,
    max_answer_seconds: float = 30.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        enable_web_search=enable_web_search,
        max_answer_seconds=max_answer_seconds,
        max_response_chars=3500,
    )


def confidence_marker(
    *,
    level: str = "high",
    source: str = "reliable",
    web_needed: str = "no",
) -> str:
    return f"[[pakko_confidence level={level} source={source} web_needed={web_needed}]]"


def make_result(
    text: str,
    *,
    level: str = "high",
    source: str = "reliable",
    web_needed: str = "no",
    web_search_used: bool = False,
    include_marker: bool = True,
) -> LLMResult:
    if include_marker:
        text = f"{text}\n{confidence_marker(level=level, source=source, web_needed=web_needed)}"
    return LLMResult(
        text=text,
        usage=LLMUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        model="test-model",
        sources=[],
        web_search_used=web_search_used,
    )


async def test_answer_uses_web_search_first_for_low_confidence_marker() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("Probably X.", level="low", source="weak", web_needed="yes")])
    summarization = FakeSummarization()
    assistant = AssistantService(make_settings(), memory, llm, summarization)  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "Probably X."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]
    assert memory.exchanges == [(123, "explain rare term frobnicator", "Probably X.")]
    assert summarization.calls == [123]


async def test_answer_uses_web_search_first_when_answer_is_confident() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("It is X.")])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "It is X."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]
    assert "pakko_confidence" not in answer


async def test_answer_does_not_retry_for_medium_confidence_with_reliable_source() -> None:
    memory = FakeMemory()
    llm = FakeLLM([
        make_result("Most likely X.", level="medium", source="reliable", web_needed="no")
    ])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "Most likely X."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]


async def test_answer_does_not_retry_when_marker_requests_web_check_after_search_first() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("Looks like X.", level="medium", source="mixed", web_needed="yes")])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "Looks like X."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]


async def test_answer_uses_web_search_for_current_data() -> None:
    memory = FakeMemory()
    llm = FakeLLM([
        make_result("Sources disagree.", level="low", source="mixed", web_search_used=True)
    ])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "find fresh data")

    assert answer == "Sources disagree."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]


async def test_answer_does_not_retry_when_marker_is_missing_after_search_first() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("Answer without marker.", include_marker=False)])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "Answer without marker."
    assert [use_web_search for _, use_web_search in llm.calls] == [True]



async def test_answer_respects_disabled_web_search_setting() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("Offline answer.", level="low", source="weak", web_needed="yes")])
    assistant = AssistantService(
        make_settings(enable_web_search=False),
        memory,
        llm,
        FakeSummarization(),
    )  # type: ignore[arg-type]

    answer = await assistant.answer(123, "explain rare term frobnicator")

    assert answer == "Offline answer."
    assert [use_web_search for _, use_web_search in llm.calls] == [False]


async def test_answer_includes_reply_context_in_current_prompt() -> None:
    memory = FakeMemory()
    llm = FakeLLM([make_result("Answer")])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "what does this mean?", reply_context="quoted detail")

    assert answer == "Answer"
    assert [use_web_search for _, use_web_search in llm.calls] == [True]
    current_prompt = llm.calls[0][0][-1]["content"]
    assert "Context from the Telegram message this request replies to:" in current_prompt
    assert "quoted detail" in current_prompt
    assert "Current user request:\nwhat does this mean?" in current_prompt
    assert memory.exchanges == [(123, "what does this mean?", "Answer")]


async def test_answer_keeps_ttl_context_reset_silent_for_user() -> None:
    memory = FakeMemory()
    memory.reset_due_to_inactivity = True
    llm = FakeLLM([make_result("New answer")])
    assistant = AssistantService(make_settings(), memory, llm, FakeSummarization())  # type: ignore[arg-type]

    answer = await assistant.answer(123, "continue")

    assert answer == "New answer"
    assert [use_web_search for _, use_web_search in llm.calls] == [True]
    assert memory.exchanges == [(123, "continue", "New answer")]
