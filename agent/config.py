import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Gemini API Keys
    GEMINI_API_KEY: str = "mock_key"
    GEMINI_BACKUP_API_KEY: str = ""

    # OpenAI API Keys
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Multi-Role Model Configuration (Industry Standard)
    GEMINI_MODEL: str = "gemini-3.5-flash"          # Default / Main
    MAIN_MODEL: str = "gemini-3.5-flash"            # Complex DAG planning & synthesis
    RESEARCH_MODEL: str = "gemini-3.1-flash-lite"   # Fast retrieval & extraction
    FALLBACK_MODEL: str = "gemini-3.6-flash"        # Robust high-availability fallback
    GEMINI_RESEARCH_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.6-flash"

    MOCK_GEMINI: bool = False
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Telegram Bot Integration
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Jira Integration
    JIRA_BASE_URL: str = "https://taskmasterjira.atlassian.net"
    JIRA_EMAIL: str = "anima.mahanty1967@gmail.com"
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = "KAN"

    # Autonomous Browser & Desktop Configuration
    BROWSER_HEADLESS: bool = False
    BROWSER_USER_DATA_DIR: str = "data/browser_profile"
    BROWSER_TIMEOUT_MS: int = 30000
    BROWSER_VIEWPORT_WIDTH: int = 1280
    BROWSER_VIEWPORT_HEIGHT: int = 800
    EMERGENCY_KILL_HOTKEY: str = "ctrl+alt+escape"

    # Spotify API Integration (Optional Web API fallback)
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
