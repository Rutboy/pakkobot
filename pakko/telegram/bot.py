from aiogram import Bot, Dispatcher

from pakko.assistant import AssistantService
from pakko.config import Settings
from pakko.llm import OpenAIResponsesClient
from pakko.memory import MemoryService, SQLiteMemoryRepository
from pakko.summarization import SummarizationService
from pakko.telegram.handlers import build_router


async def run_bot(settings: Settings) -> None:
    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    dispatcher = Dispatcher()

    repository = SQLiteMemoryRepository(settings.database_path)
    await repository.init()

    llm = OpenAIResponsesClient(settings)
    memory = MemoryService(settings, repository)
    summarization = SummarizationService(settings, repository, llm)
    assistant = AssistantService(settings, memory, llm, summarization)

    dispatcher.include_router(build_router(settings, assistant, repository))
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
