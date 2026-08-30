"""
Shared Google OAuth2 helper for Gmail, Sheets, Calendar, and Docs tools.

Supports:
  1. Desktop OAuth Flow (credentials.json -> token.json)
  2. Google Application Default Credentials (gcloud ADC fallback)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("taskmaster.google_auth")

# Base directory is the project root (parent of agent/)
from pathlib import Path
_BASE_DIR = str(Path(__file__).resolve().parent.parent.parent)
CREDENTIALS_PATH = os.path.join(_BASE_DIR, "credentials.json")
if not os.path.exists(CREDENTIALS_PATH):
    import glob
    client_secrets = glob.glob(os.path.join(_BASE_DIR, "client_secret_*.json"))
    if client_secrets:
        CREDENTIALS_PATH = client_secrets[0]
TOKEN_PATH = os.path.join(_BASE_DIR, "token.json")

# Standard Google Workspace & YouTube Data API scopes
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    import google.auth
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    logger.warning("google-auth-oauthlib not installed. Google Workspace tools will be unavailable.")


def get_google_credentials():
    """
    Returns valid Google OAuth2 credentials for the current user.
    Attempts:
      1. Saved token.json
      2. InstalledAppFlow with credentials.json
      3. Application Default Credentials (gcloud ADC) fallback
    """
    if not GOOGLE_AUTH_AVAILABLE:
        logger.error("Google auth libraries not installed.")
        return None

    creds = None

    # 1. Load saved token if it exists
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                return creds
        except Exception as e:
            logger.warning(f"Failed to load token.json: {e}. Trying fallback.")
            creds = None

    # 2. InstalledAppFlow if credentials.json exists
    if os.path.exists(CREDENTIALS_PATH):
        try:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
            logger.info("Google OAuth consent completed successfully.")
            return creds
        except Exception as e:
            logger.warning(f"OAuth flow failed: {e}. Trying ADC fallback.")

    # 3. Fallback: Application Default Credentials (gcloud auth)
    try:
        adc_creds, _ = google.auth.default(scopes=SCOPES)
        if not adc_creds.valid:
            adc_creds.refresh(Request())
        if adc_creds.valid:
            logger.info("Successfully authenticated via Google Application Default Credentials.")
            return adc_creds
    except Exception as e:
        logger.error(f"Application Default Credentials failed: {e}")

    logger.error("No valid Google credentials found. Place credentials.json in project root or run 'gcloud auth application-default login'.")
    return None


def build_service(service_name: str, version: str):
    """
    Build a Google API service client (e.g., docs v1, sheets v4, gmail v1, calendar v3, drive v3, youtube v3).
    Returns None if auth fails.
    """
    try:
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("google-api-python-client not installed.")
        return None

    creds = get_google_credentials()
    if not creds:
        return None

    try:
        return build(service_name, version, credentials=creds)
    except Exception as e:
        logger.error(f"Failed to build {service_name} {version} service: {e}")
        return None
