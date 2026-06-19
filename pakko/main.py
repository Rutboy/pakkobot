import asyncio
import logging

from pakko.config import load_settings
from pakko.logging import configure_logging
from pakko.telegram.bot import run_bot

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    logger.info("starting Pakko bot")
    await run_bot(settings)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
