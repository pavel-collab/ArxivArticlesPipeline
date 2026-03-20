"""Configuration module using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "arxiv"
    postgres_password: str = "arxiv"
    postgres_db: str = "arxiv"

    # Telegram Bot
    telegram_bot_token: str
    telegram_chat_id: str

    # OpenAI / OpenRouter
    openai_api_key: str
    openai_api_base: str = "https://openrouter.ai/api/v1"
    openai_model: str = "openai/gpt-4o-mini"

    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
