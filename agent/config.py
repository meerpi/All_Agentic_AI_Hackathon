import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("taskmaster.config")
_BASE_DIR = str(Path(__file__).resolve().parent.parent)


def ensure_vault_unpacked():
    """
    Automatically unpacks .env, credentials.json, and token.json from data/auth/vault.json
    if they are not already present on disk. Ensures zero-setup execution on clone and cloud containers.
    """
    vault_path = os.path.join(_BASE_DIR, "data", "auth", "vault.json")
    if os.path.exists(vault_path):
        try:
            with open(vault_path, "r", encoding="utf-8") as f:
                vault = json.load(f)

            # 1. Auto-unpack .env
            env_target = os.path.join(_BASE_DIR, ".env")
            env_b64 = vault.get("env_b64")
            if env_b64 and not os.path.exists(env_target):
                env_content = base64.b64decode(env_b64).decode("utf-8")
                with open(env_target, "w", encoding="utf-8") as f:
                    f.write(env_content)
                logger.info(f"Unpacked .env from vault to {env_target}")

            # 2. Auto-unpack credentials.json
            creds_target = os.path.join(_BASE_DIR, "credentials.json")
            creds_b64 = vault.get("credentials_b64")
            if creds_b64 and not os.path.exists(creds_target):
                creds_content = base64.b64decode(creds_b64).decode("utf-8")
                with open(creds_target, "w", encoding="utf-8") as f:
                    f.write(creds_content)
                logger.info(f"Unpacked credentials.json from vault to {creds_target}")

            # 3. Auto-unpack token.json
            token_target = os.path.join(_BASE_DIR, "token.json")
            token_b64 = vault.get("token_b64")
            if token_b64 and not os.path.exists(token_target):
                token_content = base64.b64decode(token_b64).decode("utf-8")
                with open(token_target, "w", encoding="utf-8") as f:
                    f.write(token_content)
                logger.info(f"Unpacked token.json from vault to {token_target}")
        except Exception as e:
            logger.warning(f"Auto-unpack of runtime vault failed: {e}")


# Run vault auto-unpack before settings instantiation
ensure_vault_unpacked()


class Settings(BaseSettings):
    # Gemini API Keys
    GEMINI_API_KEY: str = "mock_key"
    GEMINI_BACKUP_API_KEY: str = ""

    # OpenAI API Keys
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Multi-Role Model Configuration (Industry Standard)
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"          # Default / Main
    MAIN_MODEL: str = "gemini-3.1-flash-lite"            # Complex DAG planning & synthesis
    RESEARCH_MODEL: str = "gemini-3.1-flash-lite"   # Fast retrieval & extraction
    FALLBACK_MODEL: str = "gemini-2.5-flash"        # Robust high-availability fallback
    GEMINI_RESEARCH_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash"

    MOCK_GEMINI: bool = False
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000


    # Jira Integration (Sourced from .env or environment)
    JIRA_BASE_URL: str = ""
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = ""

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
