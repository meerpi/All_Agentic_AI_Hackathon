"""
Modern ARIA Snapshot & Interactive Element Parser for Taskmaster.

Uses Playwright's modern `locator(":root").aria_snapshot()` (YAML accessible hierarchy)
and assigns monotonic reference IDs (`[ref=e1]`, `[ref=e2]`, etc.) to interactable elements.
Encapsulates all page text in `<untrusted_page_observation>` tags for prompt injection defense.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from playwright.async_api import Page, Locator

logger = logging.getLogger("taskmaster.browser.aria")

# Interactive HTML tags and roles for locator extraction
INTERACTIVE_SELECTOR = (
    "a[href], button:not([disabled]), input:not([type='hidden']):not([disabled]), "
    "textarea:not([disabled]), select:not([disabled]), [role='button'], [role='link'], "
    "[role='checkbox'], [role='radio'], [role='tab'], [role='menuitem'], [role='searchbox'], "
    "[contenteditable='true'], ytd-video-renderer a#video-title, ytd-thumbnail, [data-testid]"
)


class ARIAParser:
    """Parses page accessibility state into token-efficient, numbered element maps."""

    def __init__(self):
        self._ref_map: Dict[str, Dict[str, Any]] = {}

    async def extract_page_state(self, page: Page) -> Dict[str, Any]:
        """
        Extracts both:
        1. High-level ARIA Snapshot (YAML string from Playwright)
        2. Indexed interactive elements with ref IDs [ref=e1], [ref=e2]...
        """
        self._ref_map.clear()

        # 1. Fetch native Playwright ARIA Snapshot
        try:
            aria_yaml = await page.locator(":root").aria_snapshot()
        except Exception as e:
            logger.warning(f"Could not extract native aria_snapshot: {e}")
            aria_yaml = "(ARIA snapshot unavailable)"

        # 2. Extract visible interactable elements via DOM evaluate
        # This gives us exact CSS selectors, roles, text names, and bounding boxes
        interactable_elements = await page.evaluate(
            """() => {
                const elements = Array.from(document.querySelectorAll(
                    "a[href], button, input, textarea, select, [role='button'], [role='link'], [role='tab'], [role='searchbox'], [contenteditable='true'], ytd-video-renderer a#video-title, [data-testid]"
                ));
                
                const results = [];
                let idx = 1;
                
                for (const el of elements) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    
                    // Filter hidden elements
                    if (
                        rect.width === 0 || 
                        rect.height === 0 || 
                        style.visibility === 'hidden' || 
                        style.display === 'none' || 
                        style.opacity === '0'
                    ) {
                        continue;
                    }

                    // Mask sensitive inputs
                    let val = el.value || '';
                    if (el.type === 'password' || el.getAttribute('autocomplete') === 'current-password') {
                        val = '***REDACTED_PASSWORD***';
                    }

                    const tagName = el.tagName.toLowerCase();
                    const role = el.getAttribute('role') || tagName;
                    const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || val || '').trim().substring(0, 100);
                    
                    // Unique selector generation
                    let selector = '';
                    if (el.id) {
                        selector = `#${CSS.escape(el.id)}`;
                    } else if (el.getAttribute('data-testid')) {
                        selector = `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
                    } else if (el.name) {
                        selector = `${tagName}[name="${CSS.escape(el.name)}"]`;
                    } else if (el.className && typeof el.className === 'string') {
                        const firstClass = el.className.split(' ').filter(c => c.trim().length > 0)[0];
                        if (firstClass) selector = `${tagName}.${CSS.escape(firstClass)}`;
                    }
                    if (!selector) {
                        selector = `${tagName}`;
                    }

                    results.push({
                        ref: `e${idx}`,
                        tag: tagName,
                        role: role,
                        name: text,
                        selector: selector,
                        type: el.type || null,
                        href: el.href || null,
                        box: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    });
                    idx++;
                    if (results.length >= 80) break; // Token safety cap
                }
                return results;
            }"""
        )

        for item in interactable_elements:
            self._ref_map[item["ref"]] = item

        # 3. Format compact indexed element table
        indexed_lines = []
        for item in interactable_elements:
            role_desc = item["role"]
            name_desc = f'"{item["name"]}"' if item["name"] else "(unnamed)"
            indexed_lines.append(f"[{item['ref']}] {role_desc}: {name_desc}")

        compact_elements_text = "\n".join(indexed_lines) if indexed_lines else "No interactable elements found."

        # 4. Wrap with untrusted page observation boundary
        prompt_observation = (
            "<untrusted_page_observation>\n"
            "### Page URL: " + page.url + "\n"
            "### Title: " + (await page.title()) + "\n\n"
            "### Interactive Elements (Reference by [ref=eN] or ref ID):\n"
            + compact_elements_text
            + "\n\n### ARIA Accessibility Hierarchy Summary:\n"
            + aria_yaml[:1500]  # Cap length for token efficiency
            + "\n</untrusted_page_observation>"
        )

        return {
            "untrusted_observation": prompt_observation,
            "elements": interactable_elements,
            "ref_map": self._ref_map,
            "aria_yaml": aria_yaml,
            "url": page.url,
        }

    def resolve_ref(self, ref_str: str) -> Optional[Dict[str, Any]]:
        """Resolve an element reference (e.g. 'e1', '1', '[ref=e1]') to its metadata."""
        clean_ref = re.sub(r"[^\w]", "", ref_str).lower()
        if clean_ref.startswith("ref"):
            clean_ref = clean_ref.replace("ref", "")
        if clean_ref.isdigit():
            clean_ref = f"e{clean_ref}"
        return self._ref_map.get(clean_ref)
