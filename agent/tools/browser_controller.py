"""
Autonomous Browser Controller Tool for Taskmaster.

Integrates:
- Modern ARIA snapshot & reference-based element interaction ([ref=e1])
- Navigation, clicking, typing, scrolling, keyboard hotkeys
- Vision coordinate adapter fallback
- Persistent profile reuse
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from agent.browser.aria_parser import ARIAParser
from agent.browser.session_manager import browser_manager
from agent.browser.vision_grounding import VisionGrounding
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.browser")


class BrowserControllerTool(BaseTool):
    name = "browser_controller"
    description = (
        "Autonomous Web Browser Controller. Supports web navigation, interacting with elements by "
        "ARIA reference (e.g. 'e1', '[ref=e1]'), CSS selector, or coordinates, typing text, scrolling, "
        "extracting content, and capturing visual screenshots."
    )

    def __init__(self):
        self.manager = browser_manager
        self.aria_parser = ARIAParser()
        self.vision = VisionGrounding()

    def run(self, action: str = "aria_snapshot", **kwargs: Any) -> Dict[str, Any]:
        """Synchronous entrypoint called by Taskmaster DAG orchestrator."""
        return self.manager.run_sync(self._run_async(action, **kwargs))

    async def _run_async(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        act = action.lower().strip()
        page = await self.manager.get_page()

        if act == "navigate":
            url = kwargs.get("url") or kwargs.get("target_url")
            if not url:
                raise ValueError("Action 'navigate' requires parameter 'url'.")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.0)
            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS",
                "action": "navigate",
                "url": page.url,
                "title": await page.title(),
                "observation": state["untrusted_observation"],
            }

        elif act == "aria_snapshot" or act == "observe":
            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS",
                "action": "aria_snapshot",
                "url": page.url,
                "title": await page.title(),
                "observation": state["untrusted_observation"],
                "elements_count": len(state["elements"]),
            }

        elif act == "click":
            target_ref = kwargs.get("target_ref") or kwargs.get("ref") or kwargs.get("target_id")
            selector = kwargs.get("selector")
            coord = kwargs.get("coordinate") or kwargs.get("coords")

            # 1. Click by reference ID (e.g. 'e1')
            if target_ref:
                ref_info = self.aria_parser.resolve_ref(str(target_ref))
                if ref_info and ref_info.get("selector"):
                    loc = page.locator(ref_info["selector"]).first
                    await loc.click(timeout=8000)
                else:
                    # Attempt click via evaluate text matching
                    await page.evaluate(
                        f"""() => {{
                            const elements = Array.from(document.querySelectorAll('a, button, input, [role="button"]'));
                            const target = elements[{int(str(target_ref).replace('e', '')) - 1}];
                            if (target) target.click();
                        }}"""
                    )
            # 2. Click by selector
            elif selector:
                await page.locator(selector).first.click(timeout=8000)
            # 3. Click by vision coordinates [x, y]
            elif coord and isinstance(coord, (list, tuple)) and len(coord) == 2:
                vp = page.viewport_size or {"width": 1280, "height": 800}
                conv = kwargs.get("coordinate_convention", "normalized_1000")
                px, py = self.vision.denormalize_coordinates(coord[0], coord[1], vp["width"], vp["height"], conv)
                await page.mouse.click(px, py)
            else:
                raise ValueError("Action 'click' requires 'target_ref', 'selector', or 'coordinate'.")

            await asyncio.sleep(1.0)
            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS",
                "action": "click",
                "url": page.url,
                "observation": state["untrusted_observation"],
            }

        elif act == "type":
            text = kwargs.get("text", "")
            target_ref = kwargs.get("target_ref") or kwargs.get("ref")
            selector = kwargs.get("selector")
            press_enter = kwargs.get("press_enter", True)

            if target_ref:
                ref_info = self.aria_parser.resolve_ref(str(target_ref))
                if ref_info and ref_info.get("selector"):
                    loc = page.locator(ref_info["selector"]).first
                    await loc.click(timeout=5000)
                    await loc.fill(text)
                    if press_enter:
                        await loc.press("Enter")
                else:
                    await page.keyboard.type(text)
                    if press_enter:
                        await page.keyboard.press("Enter")
            elif selector:
                loc = page.locator(selector).first
                await loc.click(timeout=5000)
                await loc.fill(text)
                if press_enter:
                    await loc.press("Enter")
            else:
                await page.keyboard.type(text)
                if press_enter:
                    await page.keyboard.press("Enter")

            await asyncio.sleep(1.0)
            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS",
                "action": "type",
                "text_entered": text,
                "url": page.url,
                "observation": state["untrusted_observation"],
            }

        elif act == "press_key" or act == "hotkey":
            key = kwargs.get("key") or kwargs.get("hotkey") or "Enter"
            await page.keyboard.press(key)
            await asyncio.sleep(0.5)
            return {
                "status": "SUCCESS",
                "action": "press_key",
                "key": key,
                "url": page.url,
            }

        elif act == "scroll":
            direction = kwargs.get("direction", "down").lower()
            amount = int(kwargs.get("amount", 500))
            delta_y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, delta_y)
            await asyncio.sleep(0.5)
            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS",
                "action": "scroll",
                "direction": direction,
                "amount": amount,
                "observation": state["untrusted_observation"],
            }

        elif act == "extract_content" or act == "scrape":
            selector = kwargs.get("selector")
            if selector:
                elements_text = await page.locator(selector).all_inner_texts()
                return {
                    "status": "SUCCESS",
                    "action": "extract_content",
                    "selector": selector,
                    "extracted_items": elements_text,
                    "url": page.url,
                }
            else:
                body_text = await page.inner_text("body")
                return {
                    "status": "SUCCESS",
                    "action": "extract_content",
                    "body_text": body_text[:5000],  # Truncate for token safety
                    "url": page.url,
                }

        elif act == "screenshot":
            annotated = kwargs.get("annotated", False)
            raw_bytes = await page.screenshot(type="jpeg", quality=80)
            if annotated:
                state = await self.aria_parser.extract_page_state(page)
                _, b64 = self.vision.render_set_of_marks(raw_bytes, state["elements"])
            else:
                import base64
                b64 = base64.b64encode(raw_bytes).decode("utf-8")

            return {
                "status": "SUCCESS",
                "action": "screenshot",
                "image_base64": b64,
                "url": page.url,
            }

        else:
            raise ValueError(f"Unknown browser action: '{action}'.")
