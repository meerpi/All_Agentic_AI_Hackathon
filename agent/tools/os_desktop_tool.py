"""
Autonomous OS Desktop Controller Tool for Taskmaster (Tier 2).

Provides:
- OS-level screen capture (MSS/Pillow)
- Hardware mouse clicks at pixel coordinates
- Keyboard typing and OS hotkey combinations
"""

import logging
from typing import Any, Dict, List, Optional
from agent.browser.desktop_driver import OSDesktopDriver
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.desktop")


class OSDesktopControllerTool(BaseTool):
    name = "os_desktop_tool"
    description = (
        "Autonomous OS Desktop Controller (Tier 2). Controls native desktop applications, screen captures, "
        "mouse clicks at specific screen coordinates, keyboard typing, and OS system hotkeys."
    )

    def __init__(self):
        self.driver = OSDesktopDriver()

    def run(self, action: str = "capture_screen", **kwargs: Any) -> Dict[str, Any]:
        act = action.lower().strip()

        if act in ("capture_screen", "screenshot", "screen_capture"):
            monitor_index = int(kwargs.get("monitor_index", 1))
            return self.driver.capture_screen(monitor_index=monitor_index)

        elif act in ("mouse_click", "click"):
            x = int(kwargs.get("x", 0))
            y = int(kwargs.get("y", 0))
            clicks = int(kwargs.get("clicks", 1))
            button = kwargs.get("button", "left")
            return self.driver.click(x=x, y=y, clicks=clicks, button=button)

        elif act in ("type_text", "type", "write"):
            text = kwargs.get("text", "")
            return self.driver.type_text(text=text)

        elif act in ("hotkey", "press_hotkey", "key_combination"):
            keys = kwargs.get("keys") or [kwargs.get("key", "Enter")]
            if isinstance(keys, str):
                keys = [keys]
            return self.driver.press_hotkey(keys=keys)

        else:
            raise ValueError(
                f"Unknown OS desktop action: '{action}'. Supported: ['capture_screen', 'mouse_click', 'type_text', 'hotkey']"
            )
