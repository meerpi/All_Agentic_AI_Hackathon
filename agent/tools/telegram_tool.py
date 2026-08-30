"""
Telegram Tool — Send messages and documents to a Telegram chat via the Bot API.

This is the ACTION side of Telegram integration (used as an output/notification channel
by workflows). For the EVENT TRIGGER side, see agent/telegram_trigger.py.

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from agent.config import settings
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.telegram")

try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Telegram tool will be unavailable.")


class TelegramTool(BaseTool):
    name = "telegram"
    description = (
        "Sends messages, notifications, and documents to a Telegram chat via the Bot API. "
        "Actions: send_message, send_document."
    )

    def _get_bot(self) -> "Bot":
        if not TELEGRAM_AVAILABLE:
            raise RuntimeError("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        if not settings.TELEGRAM_BOT_TOKEN:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN not set. Get one from @BotFather on Telegram and add it to .env"
            )
        return Bot(token=settings.TELEGRAM_BOT_TOKEN)

    def _get_chat_id(self, chat_id: Optional[str] = None) -> str:
        cid = chat_id or settings.TELEGRAM_CHAT_ID
        if not cid:
            raise RuntimeError(
                "TELEGRAM_CHAT_ID not set. Send a message to your bot, then visit "
                "https://api.telegram.org/bot<TOKEN>/getUpdates to find your chat_id. "
                "Add it to .env as TELEGRAM_CHAT_ID."
            )
        return cid

    def run(
        self,
        action: str = "send_message",
        text: Optional[str] = None,
        message: Optional[str] = None,
        chat_id: Optional[str] = None,
        file_path: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = action.lower()
        # Support both 'text' and 'message' parameter names
        content = text or message or ""

        if action == "send_message":
            return self._send_message(content, chat_id, parse_mode)
        elif action == "send_document":
            return self._send_document(file_path or "", chat_id, caption)
        else:
            return {"error": f"Unknown action '{action}'. Supported: send_message, send_document"}

    # ---------- Private action implementations ----------

    def _send_message(self, text: str, chat_id: Optional[str], parse_mode: Optional[str]) -> Dict[str, Any]:
        """Send a text message to a Telegram chat."""
        if not text:
            return {"error": "text is required for send_message action"}

        bot = self._get_bot()
        target_chat = self._get_chat_id(chat_id)

        # python-telegram-bot v21+ is fully async, so we need to run in an event loop
        async def _send():
            async with bot:
                msg = await bot.send_message(
                    chat_id=target_chat,
                    text=text,
                    parse_mode=parse_mode,
                )
                return msg

        try:
            # Handle both cases: running inside an existing event loop or not
            try:
                loop = asyncio.get_running_loop()
                # We're inside an async context — create a new thread to run the coroutine
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result_msg = loop.run_in_executor(pool, lambda: asyncio.run(_send()))
                    # This won't work cleanly; use a simpler approach
                    raise RuntimeError("use_fallback")
            except RuntimeError:
                result_msg = asyncio.run(_send())

            return {
                "action": "send_message",
                "chat_id": target_chat,
                "message_id": result_msg.message_id,
                "text_preview": text[:100] + ("..." if len(text) > 100 else ""),
                "status": "SENT",
            }
        except Exception as e:
            return {
                "action": "send_message",
                "status": "FAILED",
                "error": str(e),
            }

    def _send_document(self, file_path: str, chat_id: Optional[str], caption: Optional[str]) -> Dict[str, Any]:
        """Send a file/document to a Telegram chat."""
        if not file_path:
            return {"error": "file_path is required for send_document action"}

        bot = self._get_bot()
        target_chat = self._get_chat_id(chat_id)

        async def _send():
            async with bot:
                with open(file_path, "rb") as doc:
                    msg = await bot.send_document(
                        chat_id=target_chat,
                        document=doc,
                        caption=caption,
                    )
                    return msg

        try:
            result_msg = asyncio.run(_send())
            return {
                "action": "send_document",
                "chat_id": target_chat,
                "message_id": result_msg.message_id,
                "file_path": file_path,
                "status": "SENT",
            }
        except Exception as e:
            return {
                "action": "send_document",
                "status": "FAILED",
                "error": str(e),
            }
