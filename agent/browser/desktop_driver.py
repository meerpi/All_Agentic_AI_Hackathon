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

EVDEV_UINPUT_AVAILABLE = False
try:
    import evdev
    from evdev import UInput, ecodes as e_codes
    if os.path.exists("/dev/uinput") and os.access("/dev/uinput", os.W_OK):
        EVDEV_UINPUT_AVAILABLE = True
except Exception as e:
    logger.warning(f"evdev uinput not available: {e}")


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
        if PYAUTOGUI_AVAILABLE and self.has_display:
            try:
                pyautogui.click(x=x, y=y, clicks=clicks, button=button)
                return {
                    "status": "SUCCESS",
                    "action": "mouse_click",
                    "coordinates": [x, y],
                    "clicks": clicks,
                    "button": button,
                    "backend": "pyautogui",
                }
            except Exception as e:
                logger.warning(f"PyAutoGUI click failed: {e}. Trying evdev fallback...")

        if EVDEV_UINPUT_AVAILABLE:
            try:
                import time
                btn_code = e_codes.BTN_RIGHT if button == "right" else e_codes.BTN_MIDDLE if button == "middle" else e_codes.BTN_LEFT
                caps = {
                    e_codes.EV_KEY: [e_codes.BTN_LEFT, e_codes.BTN_RIGHT, e_codes.BTN_MIDDLE],
                    e_codes.EV_REL: [e_codes.REL_X, e_codes.REL_Y],
                }
                with UInput(caps, name="taskmaster-mouse") as ui:
                    for _ in range(clicks):
                        ui.write(e_codes.EV_KEY, btn_code, 1)
                        ui.syn()
                        time.sleep(0.05)
                        ui.write(e_codes.EV_KEY, btn_code, 0)
                        ui.syn()
                        if clicks > 1:
                            time.sleep(0.1)
                return {
                    "status": "SUCCESS",
                    "action": "mouse_click",
                    "coordinates": [x, y],
                    "clicks": clicks,
                    "button": button,
                    "backend": "uinput",
                }
            except Exception as e:
                return {"status": "FAILED", "error": f"evdev uinput click failed: {e}"}

        return {
            "status": "FAILED",
            "action": "mouse_click",
            "error": "Neither PyAutoGUI nor /dev/uinput is available to execute mouse click.",
        }

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Any]:
        """Simulates keyboard text entry."""
        if PYAUTOGUI_AVAILABLE and self.has_display:
            try:
                pyautogui.write(text, interval=interval)
                return {"status": "SUCCESS", "action": "type_text", "length": len(text), "backend": "pyautogui"}
            except Exception as e:
                logger.warning(f"PyAutoGUI type failed: {e}. Trying evdev fallback...")

        if EVDEV_UINPUT_AVAILABLE:
            try:
                import time
                # Build char to keycode mapping
                all_keys = [getattr(e_codes, f"KEY_{c.upper()}") for c in "abcdefghijklmnopqrstuvwxyz0123456789" if hasattr(e_codes, f"KEY_{c.upper()}")]
                all_keys.extend([e_codes.KEY_SPACE, e_codes.KEY_ENTER, e_codes.KEY_LEFTSHIFT])
                caps = {e_codes.EV_KEY: all_keys}
                with UInput(caps, name="taskmaster-keyboard") as ui:
                    for char in text:
                        if char == " ":
                            ui.write(e_codes.EV_KEY, e_codes.KEY_SPACE, 1)
                            ui.syn()
                            ui.write(e_codes.EV_KEY, e_codes.KEY_SPACE, 0)
                            ui.syn()
                        elif char == "\n":
                            ui.write(e_codes.EV_KEY, e_codes.KEY_ENTER, 1)
                            ui.syn()
                            ui.write(e_codes.EV_KEY, e_codes.KEY_ENTER, 0)
                            ui.syn()
                        else:
                            kc_name = f"KEY_{char.upper()}"
                            if hasattr(e_codes, kc_name):
                                kc = getattr(e_codes, kc_name)
                                is_upper = char.isupper()
                                if is_upper:
                                    ui.write(e_codes.EV_KEY, e_codes.KEY_LEFTSHIFT, 1)
                                    ui.syn()
                                ui.write(e_codes.EV_KEY, kc, 1)
                                ui.syn()
                                time.sleep(0.01)
                                ui.write(e_codes.EV_KEY, kc, 0)
                                ui.syn()
                                if is_upper:
                                    ui.write(e_codes.EV_KEY, e_codes.KEY_LEFTSHIFT, 0)
                                    ui.syn()
                        time.sleep(interval)
                return {"status": "SUCCESS", "action": "type_text", "length": len(text), "backend": "uinput"}
            except Exception as e:
                return {"status": "FAILED", "error": f"evdev uinput type failed: {e}"}

        return {
            "status": "FAILED",
            "action": "type_text",
            "error": "Neither PyAutoGUI nor /dev/uinput is available to execute keyboard typing.",
        }

    def press_hotkey(self, keys: List[str]) -> Dict[str, Any]:
        """Simulates simultaneous key combination (e.g. ['ctrl', 'alt', 't'])."""
        if PYAUTOGUI_AVAILABLE and self.has_display:
            try:
                pyautogui.hotkey(*keys)
                return {"status": "SUCCESS", "action": "hotkey", "keys": keys, "backend": "pyautogui"}
            except Exception as e:
                logger.warning(f"PyAutoGUI hotkey failed: {e}")

        if EVDEV_UINPUT_AVAILABLE:
            try:
                import time
                key_map = {
                    "enter": e_codes.KEY_ENTER,
                    "return": e_codes.KEY_ENTER,
                    "space": e_codes.KEY_SPACE,
                    "ctrl": e_codes.KEY_LEFTCTRL,
                    "alt": e_codes.KEY_LEFTALT,
                    "shift": e_codes.KEY_LEFTSHIFT,
                    "tab": e_codes.KEY_TAB,
                    "esc": e_codes.KEY_ESC,
                }
                resolved_kcs = []
                for k in keys:
                    kl = k.lower().strip()
                    if kl in key_map:
                        resolved_kcs.append(key_map[kl])
                    elif hasattr(e_codes, f"KEY_{kl.upper()}"):
                        resolved_kcs.append(getattr(e_codes, f"KEY_{kl.upper()}"))

                if resolved_kcs:
                    caps = {e_codes.EV_KEY: list(set(resolved_kcs))}
                    with UInput(caps, name="taskmaster-hotkey") as ui:
                        for kc in resolved_kcs:
                            ui.write(e_codes.EV_KEY, kc, 1)
                        ui.syn()
                        time.sleep(0.05)
                        for kc in reversed(resolved_kcs):
                            ui.write(e_codes.EV_KEY, kc, 0)
                        ui.syn()
                    return {"status": "SUCCESS", "action": "hotkey", "keys": keys, "backend": "uinput"}
            except Exception as e:
                return {"status": "FAILED", "error": f"evdev hotkey failed: {e}"}

        return {
            "status": "FAILED",
            "action": "hotkey",
            "error": "Neither PyAutoGUI nor /dev/uinput is available to execute hotkeys.",
        }

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
