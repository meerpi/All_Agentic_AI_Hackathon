"""
Autonomous OS Desktop Controller Tool for Taskmaster (Tier 2).

Provides:
- OS-level screen capture (MSS/Pillow)
- Hardware mouse clicks at pixel coordinates
- Keyboard typing and OS hotkey combinations
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from agent.browser.desktop_driver import OSDesktopDriver
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.desktop")


class OSDesktopControllerTool(BaseTool):
    name = "os_desktop_tool"
    description = (
        "Autonomous OS Desktop Controller (Tier 2). "
        "Allows the agent to control the user's laptop OS: launch applications (e.g. text editors, IDEs, browsers), "
        "write files to disk, open text files in the system editor (e.g. VS Code, nano), capture the desktop screen, "
        "and simulate mouse clicks and keystrokes. "
        "Actions: launch_application, open_editor, write_file, capture_screen, mouse_click, type_text, hotkey."
    )

    def __init__(self):
        self.driver = OSDesktopDriver()

    def run(
        self,
        action: str = "capture_screen",
        binary_name: Optional[str] = None,
        args: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        content: Optional[str] = None,
        text: Optional[str] = None,
        x: int = 0,
        y: int = 0,
        clicks: int = 1,
        button: str = "left",
        keys: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        act = action.lower().strip()

        if act in ("write_file", "save_file", "create_file"):
            target_path = file_path or kwargs.get("path") or "output.txt"
            p = Path(target_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            body = content if content is not None else text if text is not None else kwargs.get("data") or ""
            p.write_text(str(body), encoding="utf-8")
            return {
                "status": "SUCCESS",
                "action": "write_file",
                "file_path": str(p),
                "bytes_written": len(str(body).encode("utf-8")),
            }

        elif act in ("open_editor", "open_file", "edit_file"):
            target_path = file_path or kwargs.get("path") or "output.txt"
            p = Path(target_path).resolve()
            body = content if content is not None else text if text is not None else kwargs.get("data")
            if body is not None:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(body), encoding="utf-8")

            # Determine editor binary cross-platform (Windows / Linux / macOS)
            chosen_editor = binary_name
            if not chosen_editor:
                if os.name == "nt":
                    for candidate in ["code.cmd", "code", "notepad.exe", "notepad"]:
                        if shutil.which(candidate):
                            chosen_editor = candidate
                            break
                    if not chosen_editor and hasattr(os, "startfile"):
                        try:
                            os.startfile(str(p))
                            return {
                                "status": "SUCCESS",
                                "action": "open_editor",
                                "file_path": str(p),
                                "editor": "system_default",
                                "launch": {"status": "SUCCESS", "method": "os.startfile"},
                            }
                        except Exception as e:
                            logger.warning(f"os.startfile failed: {e}")
                    if not chosen_editor:
                        chosen_editor = "notepad.exe"
                else:
                    for candidate in ["code", "gedit", "kate", "mousepad", "nano", "xdg-open", "open"]:
                        if shutil.which(candidate):
                            chosen_editor = candidate
                            break
                    if not chosen_editor:
                        chosen_editor = "nano"

            launch_args = args or [str(p)]
            res = self.driver.launch_application(binary_name=chosen_editor, args=launch_args)
            return {
                "status": "SUCCESS",
                "action": "open_editor",
                "file_path": str(p),
                "editor": chosen_editor,
                "launch": res,
            }

        elif act in ("launch_application", "launch_app", "open_application", "open_app", "launch", "open"):
            b_name = (
                binary_name
                or kwargs.get("app_name")
                or kwargs.get("application")
                or kwargs.get("app")
                or kwargs.get("name")
                or kwargs.get("command")
            )
            if not b_name:
                raise ValueError("Action 'launch_application' requires parameter 'binary_name' or 'app_name'.")
            cmd_args = args or kwargs.get("args") or []
            if isinstance(cmd_args, str):
                cmd_args = [cmd_args]
            return self.driver.launch_application(binary_name=b_name, args=cmd_args)

        elif act in ("capture_screen", "screenshot", "screen_capture"):
            monitor_index = int(kwargs.get("monitor_index", 1))
            return self.driver.capture_screen(monitor_index=monitor_index)

        elif act in ("annotate_image", "annotate_screenshot", "annotate", "set_of_marks"):
            from agent.browser.vision_grounding import VisionGrounding
            import base64
            img_b64 = kwargs.get("image_base64") or kwargs.get("image") or kwargs.get("screenshot")
            elements = kwargs.get("elements") or kwargs.get("marks") or []
            if not img_b64:
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
            return self.driver.click(x=x, y=y, clicks=clicks, button=button)

        elif act in ("type_text", "type", "write"):
            txt = text or content or kwargs.get("text", "")
            return self.driver.type_text(text=txt)

        elif act in ("hotkey", "press_hotkey", "key_combination"):
            k_list = keys or kwargs.get("keys") or [kwargs.get("key", "Enter")]
            if isinstance(k_list, str):
                k_list = [k_list]
            return self.driver.press_hotkey(keys=k_list)

        else:
            raise ValueError(
                f"Unknown OS desktop action: '{action}'. Supported: ['open_editor', 'write_file', 'launch_application', 'capture_screen', 'annotate_image', 'mouse_click', 'type_text', 'hotkey']"
            )
