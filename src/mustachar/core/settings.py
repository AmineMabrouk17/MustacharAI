"""Application settings loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings for the MustacharAI application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "MustacharAI"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    groq_api_key: str = ""
    groq_chat_model: str = "allam-2-7b"
    groq_stt_model: str = "whisper-large-v3"
    chroma_persist_dir: str = "data/chroma_db"


settings = Settings()
