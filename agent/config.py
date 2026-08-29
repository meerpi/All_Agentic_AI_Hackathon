import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str = "mock_key"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MOCK_GEMINI: bool = True
    AGENT_MAX_ITERATIONS: int = 10
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
