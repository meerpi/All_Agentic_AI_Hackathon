"""
Persistent Browser Session Manager for Taskmaster.

Handles:
- Asynchronous Playwright lifecycle (launch, persistent context, tabs)
- Dedicated persistent browser profile storage (data/browser_profile/)
- Thread-safe sync bridge (run_sync) for DAG orchestrator tools
- Anti-detection Chrome arguments
- Emergency Panic Kill Switch
"""

import asyncio
import base64
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple, TypeVar

from agent.config import settings

logger = logging.getLogger("taskmaster.browser.session")

T = TypeVar("T")


class BrowserSessionManager:
    """Manages the persistent Playwright browser instance and execution event loop."""

    def __init__(self):
        self.profile_dir = Path(settings.BROWSER_USER_DATA_DIR)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        
        self._playwright = None
        self._context = None
        self._active_page = None
        self._lock = asyncio.Lock()
        
        # Dedicated thread and event loop for synchronous tool execution
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        self._is_killed = False

    def _ensure_background_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure a dedicated background event loop is running for sync-to-async bridges."""
        with self._thread_lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()

                def _run_loop(loop: asyncio.AbstractEventLoop):
                    asyncio.set_event_loop(loop)
                    loop.run_forever()

                self._thread = threading.Thread(target=_run_loop, args=(self._loop,), daemon=True)
                self._thread.start()
                logger.info("Initialized dedicated background event loop for browser automation.")
            return self._loop

    def run_sync(self, coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
        """
        Thread-safe synchronous bridge for executing async Playwright methods.
        Can be called safely from any sync thread or FastAPI worker.
        """
        if self._is_killed:
            raise RuntimeError("Browser session was terminated by Emergency Kill Switch.")
            
        loop = self._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        effective_timeout = timeout or (settings.BROWSER_TIMEOUT_MS / 1000.0)
        try:
            return future.result(timeout=effective_timeout)
        except Exception as e:
            logger.error(f"Error executing browser coroutine synchronously: {e}")
            raise

    async def get_page(self, headed: Optional[bool] = None):
        """
        Returns active Playwright page, initializing persistent context if needed.
        """
        if self._is_killed:
            self._is_killed = False

        from playwright.async_api import async_playwright

        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

            if self._context is None:
                is_headless = settings.BROWSER_HEADLESS if headed is None else not headed
                
                # Anti-detection & media-codec launch arguments
                args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]

                logger.info(f"Launching persistent browser context at: {self.profile_dir} (headless={is_headless})")
                try:
                    self._context = await self._playwright.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir),
                        headless=is_headless,
                        args=args,
                        viewport={
                            "width": settings.BROWSER_VIEWPORT_WIDTH,
                            "height": settings.BROWSER_VIEWPORT_HEIGHT,
                        },
                        ignore_default_args=["--enable-automation"],
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    )
                except Exception as e:
                    logger.warning(f"Failed to launch with persistent context: {e}. Retrying without profile locks...")
                    # Fallback launch
                    self._context = await self._playwright.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir / "fallback"),
                        headless=is_headless,
                        args=args,
                    )

            # Retrieve or create active page
            if not self._context.pages:
                self._active_page = await self._context.new_page()
            else:
                self._active_page = self._context.pages[0]

        return self._active_page

    async def capture_screenshot_base64(self, full_page: bool = False) -> str:
        """Capture screenshot of the current page as a base64 encoded JPEG."""
        page = await self.get_page()
        screenshot_bytes = await page.screenshot(type="jpeg", quality=80, full_page=full_page)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def get_session_status(self) -> Dict[str, Any]:
        """Returns metadata about the active browser session."""
        if not self._context or not self._active_page:
            return {
                "active": False,
                "current_url": None,
                "title": None,
                "page_count": 0,
                "profile_dir": str(self.profile_dir),
            }
        try:
            url = self._active_page.url
            title = await self._active_page.title()
            return {
                "active": True,
                "current_url": url,
                "title": title,
                "page_count": len(self._context.pages),
                "profile_dir": str(self.profile_dir),
            }
        except Exception as e:
            return {
                "active": False,
                "error": str(e),
                "profile_dir": str(self.profile_dir),
            }

    async def close_session(self):
        """Gracefully closes page, context, and Playwright session."""
        try:
            if self._context:
                await self._context.close()
                self._context = None
                self._active_page = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Browser session closed cleanly.")
        except Exception as e:
            logger.warning(f"Error during browser session shutdown: {e}")

    def emergency_kill(self) -> Dict[str, Any]:
        """
        Emergency Panic Kill Switch.
        Immediately stops the background event loop, closes contexts, and sets kill flag.
        """
        self._is_killed = True
        logger.warning("🚨 EMERGENCY PANIC KILL SWITCH ACTIVATED! Terminating browser automation.")
        
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.close_session(), self._loop)
        except Exception as e:
            logger.error(f"Error during emergency close: {e}")

        # Reset pointers
        self._context = None
        self._active_page = None
        self._playwright = None

        return {
            "status": "KILLED",
            "message": "Browser session successfully terminated by Emergency Kill Switch.",
        }


# Global singleton instance
browser_manager = BrowserSessionManager()
