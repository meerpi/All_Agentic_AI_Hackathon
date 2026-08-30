"""
OS Desktop Vision & Hardware Event Controller for Taskmaster (Tier 2).

Provides:
- Screen capture via MSS / Pillow
- Mouse click, double click, dragging, typing, and OS hotkeys via PyAutoGUI
- Safe degradation in headless / display-less environments
"""

import base64
import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

logger = logging.getLogger("taskmaster.browser.desktop")

PYAUTOGUI_AVAILABLE = False
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except Exception as e:
    logger.warning(f"PyAutoGUI not available on this display server: {e}")

MSS_AVAILABLE = False
try:
    import mss
    MSS_AVAILABLE = True
except Exception as e:
    logger.warning(f"MSS screenshot library not available: {e}")


class OSDesktopDriver:
    """Controls OS-level desktop window interactions, screen capture, and input events."""

    def __init__(self):
        self.has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.name == "nt")

    def capture_screen(self, monitor_index: int = 1) -> Dict[str, Any]:
        """Captures a screenshot of the OS desktop display."""
        if not self.has_display and not MSS_AVAILABLE:
            return {
                "status": "SANDBOX_NOTICE",
                "message": "No active GUI display detected in current environment.",
                "image_base64": None,
                "resolution": {"width": 1920, "height": 1080},
            }

        try:
            with mss.MSS() as sct:
                monitors = sct.monitors
                target_mon = monitors[monitor_index] if monitor_index < len(monitors) else monitors[0]
                sct_img = sct.grab(target_mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

                return {
                    "status": "SUCCESS",
                    "resolution": {"width": img.width, "height": img.height},
                    "image_base64": b64,
                }
        except Exception as e:
            logger.error(f"Error capturing desktop screen: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "resolution": {"width": 1920, "height": 1080},
            }

    def click(self, x: int, y: int, clicks: int = 1, button: str = "left") -> Dict[str, Any]:
        """Simulates hardware mouse click at specified screen pixel coordinates."""
        if not PYAUTOGUI_AVAILABLE or not self.has_display:
            return {
                "status": "FAILED",
                "action": "mouse_click",
                "error": "PyAutoGUI or active graphical display server is not available to execute mouse click.",
            }

        try:
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            return {
                "status": "SUCCESS",
                "action": "mouse_click",
                "coordinates": [x, y],
                "clicks": clicks,
                "button": button,
            }
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Any]:
        """Simulates keyboard text entry."""
        if not PYAUTOGUI_AVAILABLE or not self.has_display:
            return {
                "status": "FAILED",
                "action": "type_text",
                "error": "PyAutoGUI or active graphical display server is not available to execute keyboard typing.",
            }

        try:
            pyautogui.write(text, interval=interval)
            return {"status": "SUCCESS", "action": "type_text", "length": len(text)}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def press_hotkey(self, keys: List[str]) -> Dict[str, Any]:
        """Simulates simultaneous key combination (e.g. ['ctrl', 'alt', 't'])."""
        if not PYAUTOGUI_AVAILABLE or not self.has_display:
            return {
                "status": "FAILED",
                "action": "hotkey",
                "error": "PyAutoGUI or active graphical display server is not available to execute hotkeys.",
            }

        try:
            pyautogui.hotkey(*keys)
            return {"status": "SUCCESS", "action": "hotkey", "keys": keys}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def launch_application(self, binary_name: str, args: list = None) -> Dict[str, Any]:
        """Launches an application as a detached process."""
        import shutil
        import subprocess
        
        if not shutil.which(binary_name):
            raise FileNotFoundError(f"Binary '{binary_name}' not found in PATH.")
        
        cmd = [binary_name] + (args or [])
        env = os.environ.copy()
        if "DISPLAY" not in env and os.name != "nt":
            env["DISPLAY"] = ":0"
            
        try:
            if os.name == "nt":
                process = subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                process = subprocess.Popen(cmd, env=env, start_new_session=True)
            return {"status": "SUCCESS", "action": "launch_application", "pid": process.pid}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}
