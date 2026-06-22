from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]
SearchContextSize = Literal["low", "medium", "high"]


class Settings(BaseSettings):
    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str = Field(default="pakkkobot", alias="TELEGRAM_BOT_USERNAME")
    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY")

    openai_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_MODEL")
    openai_reasoning_effort: ReasoningEffort = Field(
        default="medium",
        alias="OPENAI_REASONING_EFFORT",
    )
    openai_timeout_seconds: float = Field(default=90.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_request_retries: int = Field(default=3, ge=0, alias="OPENAI_REQUEST_RETRIES")
    max_answer_seconds: float = Field(default=45.0, ge=5.0, alias="MAX_ANSWER_SECONDS")
    openai_input_price_usd_per_million: float = Field(
        default=0.75,
        alias="OPENAI_INPUT_PRICE_USD_PER_MILLION",
    )
    openai_output_price_usd_per_million: float = Field(
        default=4.50,
        alias="OPENAI_OUTPUT_PRICE_USD_PER_MILLION",
    )

    database_path: Path = Field(default=Path("data/pakko.sqlite3"), alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    enable_web_search: bool = Field(default=True, alias="ENABLE_WEB_SEARCH")
    web_search_context_size: SearchContextSize = Field(
        default="medium",
        alias="WEB_SEARCH_CONTEXT_SIZE",
    )

    context_ttl_seconds: int = Field(default=600, ge=60, alias="CONTEXT_TTL_SECONDS")
    max_recent_messages: int = Field(default=12, ge=2, alias="MAX_RECENT_MESSAGES")
    summarize_after_messages: int = Field(default=24, ge=4, alias="SUMMARIZE_AFTER_MESSAGES")
    max_response_chars: int = Field(default=3500, ge=500, alias="MAX_RESPONSE_CHARS")
    max_input_file_bytes: int = Field(
        default=20_000_000,
        ge=1_000_000,
        alias="MAX_INPUT_FILE_BYTES",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("telegram_bot_username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if username.startswith("@"):
            username = username[1:]
        if not username:
            raise ValueError("Telegram bot username must not be empty")
        return username


@lru_cache
def load_settings() -> Settings:
    return Settings()
