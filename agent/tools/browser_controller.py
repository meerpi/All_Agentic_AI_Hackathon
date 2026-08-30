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
        # Auto-detect navigate intent: if url is provided but action wasn't explicitly set to navigate
        url = kwargs.get("url") or kwargs.get("target_url")
        if url and action in ("aria_snapshot", "observe"):
            action = "navigate"
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

            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)

            # Check HTTP status code from navigation response
            http_status = response.status if response else 0
            page_title = await page.title()
            current_url = page.url

            # Detect HTTP error pages (4xx, 5xx) or error page title patterns
            error_title_patterns = ["error", "bad request", "not found", "forbidden", "denied", "unavailable", "blocked"]
            is_http_error = http_status >= 400
            is_error_title = any(p in page_title.lower() for p in error_title_patterns)

            if is_http_error or is_error_title:
                logger.warning(f"Navigation error: HTTP {http_status}, title='{page_title}', url={current_url}")

                # Fallback: search Google for the intended content
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                # Build a search query from the URL path components
                path_parts = [p for p in parsed.path.strip("/").split("/") if p and len(p) > 2]
                search_query = f"{parsed.hostname or ''} {' '.join(path_parts)}".strip()
                if not search_query:
                    search_query = url

                logger.info(f"Falling back to Google search: '{search_query}'")
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_query)}"
                await page.goto(google_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2.0)

                # Try clicking the first real search result link
                try:
                    # Google search result links are in <a> tags with h3 children
                    first_result = await page.query_selector("div#search a h3")
                    if first_result:
                        parent_link = await first_result.evaluate_handle("el => el.closest('a')")
                        if parent_link:
                            await parent_link.as_element().click()
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                            await asyncio.sleep(2.0)
                            logger.info(f"Fallback navigation landed on: {page.url}")
                except Exception as e:
                    logger.warning(f"Could not click first Google result: {e}")

            # Detect interstitial/ad redirect pages and wait for real content
            current_url_lower = page.url.lower()
            interstitial_patterns = ["interstitial", "consent", "/ads/", "redirect", "splash", "gateway", "landing"]
            is_interstitial = any(p in current_url_lower for p in interstitial_patterns)

            if is_interstitial:
                logger.info(f"Interstitial page detected at {page.url}. Waiting for redirect...")
                for _ in range(6):
                    await asyncio.sleep(2.0)
                    new_url = page.url.lower()
                    if not any(p in new_url for p in interstitial_patterns):
                        logger.info(f"Redirect completed: {page.url}")
                        break
                await asyncio.sleep(1.0)

            # Final check: did we end up on a useful page?
            final_title = await page.title()
            final_status_ok = not any(p in final_title.lower() for p in error_title_patterns)

            state = await self.aria_parser.extract_page_state(page)
            return {
                "status": "SUCCESS" if final_status_ok else "FAILED",
                "action": "navigate",
                "url": page.url,
                "title": final_title,
                "original_url": url,
                "http_status": http_status,
                "used_fallback": is_http_error or is_error_title,
                "observation": state["untrusted_observation"],
                "page_content": state["untrusted_observation"][:3000],
            }

        elif act == "aria_snapshot" or act == "observe":
            state = await self.aria_parser.extract_page_state(page)
            obs = state["untrusted_observation"]
            return {
                "status": "SUCCESS",
                "action": "aria_snapshot",
                "url": page.url,
                "title": await page.title(),
                "observation": obs,
                "page_content": obs,
                "content": obs,
                "extracted_content": obs,
                "text": obs,
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
                loc = page.locator(selector).first
                is_optional = kwargs.get("optional", False) or any(
                    k in selector.lower() for k in ["skip", "ad-", "ad_", "banner", "cookie", "consent", "close-button", "ad'"]
                )
                try:
                    if is_optional:
                        count = await page.locator(selector).count()
                        if count > 0:
                            await loc.click(timeout=3000)
                        else:
                            return {
                                "status": "SUCCESS",
                                "action": "click",
                                "clicked": False,
                                "url": page.url,
                                "note": f"Optional element '{selector}' not present on page (no action needed).",
                            }
                    else:
                        await loc.click(timeout=8000)
                except Exception as e:
                    if is_optional:
                        return {
                            "status": "SUCCESS",
                            "action": "click",
                            "clicked": False,
                            "url": page.url,
                            "note": f"Optional element '{selector}' was not clickable: {e}",
                        }
                    raise
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
