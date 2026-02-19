from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://euportal:euportal_secret@localhost:5432/eu_bagatell"
    secret_key: str = "change-me-to-a-random-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    openai_api_key: str = ""
    openai_model: str = "gpt-5.2"

    tavily_api_key: str = ""  # Optional: enables real-time web search in legal analysis

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    generated_forms_dir: str = "generated_forms"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
