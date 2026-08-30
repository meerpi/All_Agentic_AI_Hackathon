"""
Specialized Spotify Autonomous Controller for Taskmaster.

Explicit Capability Split:
- Search, Queueing & Playlists: Handled by Web Player (open.spotify.com) or Spotify Web API
- Fast-Path Transport Controls: Handled by Linux MPRIS D-Bus (sub-50ms) or Web Player controls
"""

import asyncio
import logging
import subprocess
from typing import Any, Dict, List, Optional
from playwright.async_api import Page
from agent.browser.session_manager import browser_manager

logger = logging.getLogger("taskmaster.browser.spotify")


class SpotifyDriver:
    """Specialized Spotify automation engine combining Web Player takeover with MPRIS fast-path."""

    def __init__(self):
        self.manager = browser_manager

    async def search_and_play(self, query: str) -> Dict[str, Any]:
        """
        Navigates to Spotify Web Player search, enters query, and clicks top result to start playback.
        """
        page: Page = await self.manager.get_page(headed=True)
        search_url = "https://open.spotify.com/search"

        logger.info(f"Navigating to Spotify Web Player search: {query}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1.5)

        # 1. Type into search input
        try:
            search_input = page.locator('input[data-testid="search-input"]')
            await search_input.click(timeout=8000)
            await search_input.fill(query)
            await search_input.press("Enter")
        except Exception:
            logger.warning("Could not find search input, falling back to direct query navigation...")
            await page.goto(f"https://open.spotify.com/search/{query}", wait_until="domcontentloaded")

        await asyncio.sleep(2.0)

        # 2. Click Top Result / Play button
        clicked_info = await page.evaluate(
            """() => {
                // Try clicking play button on top result card
                const topCardPlay = document.querySelector('div[data-testid="top-result-card"] button[data-testid="play-button"]');
                if (topCardPlay) {
                    topCardPlay.click();
                    return { action: 'top_result_card_play', clicked: true };
                }
                
                // Fallback: Click first track row in list
                const firstRow = document.querySelector('div[data-testid="tracklist-row"]');
                if (firstRow) {
                    firstRow.click();
                    return { action: 'track_row_click', clicked: true };
                }
                
                // Fallback: Generic play button
                const anyPlay = document.querySelector('button[aria-label*="Play"]');
                if (anyPlay) {
                    anyPlay.click();
                    return { action: 'generic_play_click', clicked: true };
                }
                return { clicked: false };
            }"""
        )

        return {
            "status": "SUCCESS",
            "action": "spotify_search_and_play",
            "query": query,
            "result_info": clicked_info,
            "url": page.url,
        }

    async def create_playlist(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new playlist in Spotify Web Player."""
        page: Page = await self.manager.get_page(headed=True)
        
        # Click Create Playlist button
        create_btn = page.locator('button[data-testid="create-playlist-button"], button[aria-label="Create playlist"]').first
        await create_btn.click(timeout=8000)
        await asyncio.sleep(1.5)

        try:
            # Open edit details modal by clicking the playlist name
            title_btn = page.locator('h1[dir="auto"], button[data-testid="edit-details-title"], span[data-testid="entityTitle"]').first
            await title_btn.click(timeout=5000)
            await asyncio.sleep(1.0)

            name_input = page.locator('input[data-testid="playlist-edit-details-name-input"], input[placeholder*="name"]')
            await name_input.fill(name)
            
            if description:
                desc_input = page.locator('textarea[data-testid="playlist-edit-details-description-input"], textarea[placeholder*="description"]')
                await desc_input.fill(description)
                
            save_btn = page.locator('button[data-testid="playlist-edit-details-save-button"], button[aria-label="Save"]')
            await save_btn.click()
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"Could not fill playlist details: {e}")

        return {
            "status": "SUCCESS",
            "action": "spotify_create_playlist",
            "playlist_name": name,
            "url": page.url,
            "note": "Playlist created. Use track search to append songs.",
        }

    def mpris_control(self, command: str) -> Dict[str, Any]:
        """
        Linux Fast-Path MPRIS D-Bus controller (sub-50ms playback control for active desktop client).
        Supported commands: 'PlayPause', 'Play', 'Pause', 'Next', 'Previous', 'Stop'
        """
        cmd_map = {
            "play_pause": "PlayPause",
            "play": "Play",
            "pause": "Pause",
            "next": "Next",
            "previous": "Previous",
            "prev": "Previous",
            "stop": "Stop",
        }
        method = cmd_map.get(command.lower().strip(), command)

        dbus_cmd = [
            "dbus-send",
            "--print-reply",
            "--dest=org.mpris.MediaPlayer2.spotify",
            "/org/mpris/MediaPlayer2",
            f"org.mpris.MediaPlayer2.Player.{method}",
        ]

        try:
            res = subprocess.run(dbus_cmd, capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                return {
                    "status": "SUCCESS",
                    "driver": "MPRIS_DBUS",
                    "command": method,
                }
            else:
                return {
                    "status": "FALLBACK_NEEDED",
                    "error": res.stderr.strip() or "Spotify MPRIS D-Bus interface not active",
                }
        except Exception as e:
            return {
                "status": "FALLBACK_NEEDED",
                "error": str(e),
            }

    async def control(self, command: str) -> Dict[str, Any]:
        """
        Playback Transport Control:
        1. Tries Linux MPRIS D-Bus fast-path (<50ms).
        2. Falls back to Web Player UI buttons if MPRIS is unavailable.
        """
        # 1. Fast-path MPRIS attempt
        mpris_res = self.mpris_control(command)
        if mpris_res.get("status") == "SUCCESS":
            return mpris_res

        # 2. Web Player UI fallback
        page: Page = await self.manager.get_page()
        cmd = command.lower().strip()

        button_selectors = {
            "play_pause": 'button[data-testid="control-button-playpause"]',
            "play": 'button[data-testid="control-button-playpause"]',
            "pause": 'button[data-testid="control-button-playpause"]',
            "next": 'button[data-testid="control-button-skip-forward"]',
            "previous": 'button[data-testid="control-button-skip-back"]',
            "prev": 'button[data-testid="control-button-skip-back"]',
        }

        sel = button_selectors.get(cmd)
        if sel:
            btn = page.locator(sel).first
            await btn.click(timeout=5000)
            return {
                "status": "SUCCESS",
                "driver": "WEB_PLAYER_UI",
                "command": cmd,
            }
        else:
            raise ValueError(f"Unsupported Spotify control command: '{command}'. Supported: {list(button_selectors.keys())}")
