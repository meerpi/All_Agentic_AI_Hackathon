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
        "Autonomous OS Desktop Controller (Tier 2). "
        "Actions: launch_application, capture_screen, annotate_image, mouse_click, type_text, hotkey."
    )

    def __init__(self):
        self.driver = OSDesktopDriver()

    def run(self, action: str = "capture_screen", **kwargs: Any) -> Dict[str, Any]:
        act = action.lower().strip()

        if act in ("launch_application", "launch_app", "open_application", "open_app", "launch", "open"):
            binary_name = (
                kwargs.get("binary_name")
                or kwargs.get("app_name")
                or kwargs.get("application")
                or kwargs.get("app")
                or kwargs.get("name")
                or kwargs.get("command")
            )
            if not binary_name:
                raise ValueError("Action 'launch_application' requires parameter 'binary_name' or 'app_name'.")
            args = kwargs.get("args") or []
            if isinstance(args, str):
                args = [args]
            return self.driver.launch_application(binary_name=binary_name, args=args)

        elif act in ("capture_screen", "screenshot", "screen_capture"):
            monitor_index = int(kwargs.get("monitor_index", 1))
            return self.driver.capture_screen(monitor_index=monitor_index)

        elif act in ("annotate_image", "annotate_screenshot", "annotate", "set_of_marks"):
            from agent.browser.vision_grounding import VisionGrounding
            import base64
            img_b64 = kwargs.get("image_base64") or kwargs.get("image") or kwargs.get("screenshot")
            elements = kwargs.get("elements") or kwargs.get("marks") or []
            if not img_b64:
                # Capture fresh screen if no image provided
                cap = self.driver.capture_screen()
                img_b64 = cap.get("image_base64")
            
            if img_b64:
                try:
                    img_bytes = base64.b64decode(img_b64)
                    vg = VisionGrounding()
                    _, annotated_b64 = vg.render_set_of_marks(img_bytes, elements)
                    return {"status": "SUCCESS", "action": "annotate_image", "image_base64": annotated_b64, "marks_count": len(elements)}
                except Exception as e:
                    return {"status": "SUCCESS", "action": "annotate_image", "image_base64": img_b64, "note": f"Fallback raw image: {e}"}
            return {"status": "FAILED", "error": "No image available to annotate."}

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
                f"Unknown OS desktop action: '{action}'. Supported: ['launch_application', 'capture_screen', 'annotate_image', 'mouse_click', 'type_text', 'hotkey']"
            )
