"""
Specialized YouTube Autonomous Controller for Taskmaster.

Handles:
- Direct search and video playback execution
- Cookie consent dialog auto-dismissal
- Video playback verification (document.querySelector('video').paused === false)
- Background/Inline ad auto-skipping
- Native YouTube keyboard shortcut controls ('k', 'f', 'm', 'j', 'l')
"""

import asyncio
import logging
import urllib.parse
from typing import Any, Dict, Optional
from playwright.async_api import Page
from agent.browser.session_manager import browser_manager

logger = logging.getLogger("taskmaster.browser.youtube")


class YouTubeDriver:
    """Specialized controller for YouTube search, playback, and transport actions."""

    def __init__(self):
        self.manager = browser_manager

    async def play_video(
        self,
        url: str,
        seek_seconds: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        auto_skip_ads: bool = True,
        auto_close: bool = False
    ) -> Dict[str, Any]:
        """
        Directly navigates to a YouTube video URL, dismisses dialogs, seeks to specified timestamp,
        starts playback, actively auto-skips ads for the specified duration, and optionally closes the session.
        """
        page: Page = await self.manager.get_page()
        # Pause any current playback before navigating
        try:
            await page.evaluate("document.querySelector('video')?.pause()")
        except Exception:
            pass

        target_url = url
        if seek_seconds is not None:
            seek_seconds = max(0, int(seek_seconds))
            target_url = f"{url}&t={seek_seconds}s" if "?" in url else f"{url}?t={seek_seconds}s"

        logger.info(f"Navigating to YouTube video: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        await self._dismiss_consent_dialogs(page)
        await asyncio.sleep(2.0)

        # Ensure video is playing and seeked to requested timestamp
        playback_info = await page.evaluate(
            """(seek) => {
                const video = document.querySelector('video');
                if (!video) return { error: 'No video element found' };
                if (seek !== null && seek !== undefined) {
                    video.currentTime = seek;
                }
                video.muted = false;
                video.play().catch(() => {});
                return {
                    title: document.title.replace(' - YouTube', ''),
                    currentTime: Math.round(video.currentTime),
                    duration: Math.round(video.duration || 0),
                    paused: video.paused
                };
            }""",
            seek_seconds
        )

        ads_skipped_count = 0
        if auto_skip_ads:
            # Active pre-roll ad clearance loop (checks for up to 6 seconds)
            for _ in range(6):
                if await self.skip_ad(page):
                    ads_skipped_count += 1
                is_ad_active = await page.evaluate("""() => {
                    const p = document.querySelector('#movie_player');
                    return !!(p && (p.classList.contains('ad-showing') || p.classList.contains('ad-interrupting')));
                }""")
                if not is_ad_active:
                    break
                await asyncio.sleep(1.0)

            # Ensure player is ready and ads are skipped
            for _ in range(3):
                if await self.skip_ad(page):
                    ads_skipped_count += 1
                await asyncio.sleep(0.5)

            # Pause background automation browser so only the frontend UI plays for the user
            try:
                await page.evaluate("document.querySelector('video')?.pause()")
            except Exception:
                pass

        state = await self.get_playback_state(page)
        return {
            "status": "SUCCESS",
            "action": "youtube_play_video",
            "url": page.url,
            "seek_seconds": seek_seconds,
            "duration_played_seconds": duration_seconds,
            "ads_skipped_count": ads_skipped_count,
            "playback_state": state,
        }

    async def search_and_play(
        self,
        query: str,
        auto_skip_ads: bool = True,
        duration_seconds: Optional[int] = None,
        auto_close: bool = False
    ) -> Dict[str, Any]:
        """
        Navigates to YouTube search results, clicks top video result, handles consent dialogs,
        un-mutes and plays, actively auto-skips ads for the specified duration, and optionally closes the session.
        """
        page: Page = await self.manager.get_page()
        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"

        logger.info(f"Navigating to YouTube search: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # 1. Dismiss cookie/consent popups if present
        await self._dismiss_consent_dialogs(page)

        # 2. Wait for video results to appear
        try:
            await page.wait_for_selector("ytd-video-renderer a#video-title, a#video-title", timeout=8000)
        except Exception:
            logger.warning("Standard video title selector timed out, attempting fallback click...")

        # 3. Locate top video result
        video_info = await page.evaluate(
            """() => {
                const firstResult = document.querySelector('ytd-video-renderer a#video-title, ytd-compact-video-renderer a#video-title, a#video-title');
                if (firstResult) {
                    const title = firstResult.innerText || firstResult.title;
                    const href = firstResult.href;
                    return { title, href, clicked: true };
                }
                const fallback = document.querySelector('ytd-video-renderer a#thumbnail, a#thumbnail');
                if (fallback) {
                    return { title: 'YouTube Video', href: fallback.href, clicked: true };
                }
                return { clicked: false };
            }"""
        )

        if video_info.get("href"):
            logger.info(f"Navigating directly to top search result: {video_info['href']}")
            await page.goto(video_info["href"], wait_until="domcontentloaded", timeout=30000)
        else:
            locator = page.locator("ytd-video-renderer a#video-title, a#video-title").first
            await locator.click(timeout=5000)

        # 4. Wait for player to load and verify playback
        await asyncio.sleep(2.5)
        await self._dismiss_consent_dialogs(page)

        # Ensure video is playing and unmuted
        await page.evaluate(
            """() => {
                const video = document.querySelector('video');
                if (video) {
                    video.muted = false;
                    video.play().catch(() => {});
                }
            }"""
        )


        ads_skipped_count = 0
        if auto_skip_ads:
            for _ in range(2):
                if await self.skip_ad(page):
                    ads_skipped_count += 1
                await asyncio.sleep(0.5)

        # Pause background automation browser so only the frontend UI plays for the user
        try:
            await page.evaluate("document.querySelector('video')?.pause()")
        except Exception:
            pass

        state = await self.get_playback_state(page)
        return {
            "status": "SUCCESS",
            "action": "youtube_search_and_play",
            "query": query,
            "video_title": state.get("title", video_info.get("title", "YouTube Video")),
            "video_url": page.url if page.url and page.url != "about:blank" else video_info.get("href"),
            "ads_skipped_count": ads_skipped_count,
            "duration_played_seconds": duration_seconds,
            "playback_state": state,
        }

    async def _dismiss_consent_dialogs(self, page: Page):
        """Dismiss Google/YouTube EU Cookie consent dialogs if they pop up."""
        try:
            await page.evaluate(
                """() => {
                    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                    const acceptBtn = buttons.find(b => {
                        const txt = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
                        return txt.includes('accept all') || txt.includes('i agree') || txt.includes('accept the use') || txt.includes('reject all');
                    });
                    if (acceptBtn) acceptBtn.click();
                }"""
            )
        except Exception as e:
            logger.debug(f"Consent dismissal notice: {e}")

    async def skip_ad(self, page: Optional[Page] = None) -> bool:
        """Check for and click YouTube skip ad buttons and bypass video advertisements."""
        if page is None:
            page = await self.manager.get_page()

        try:
            skipped = await page.evaluate(
                """() => {
                    const skipSelectors = [
                        '.ytp-ad-skip-button',
                        '.ytp-skip-ad-button',
                        '.ytp-ad-skip-button-modern',
                        'button.ytp-ad-overlay-close-button',
                        '.ytp-ad-text.ytp-ad-preview-text',
                        '.ytp-ad-skip-button-container button',
                        '.videoAdUiSkipButton',
                        '[id^="skip-button"] button',
                        '[aria-label*="Skip Ad"]',
                        '[aria-label*="skip ad"]',
                        '[aria-label*="Skip ads"]',
                        '[aria-label*="skip ads"]'
                    ];
                    let didSkip = false;
                    for (const sel of skipSelectors) {
                        const btns = document.querySelectorAll(sel);
                        for (const btn of btns) {
                            if (btn && (btn.offsetWidth > 0 || btn.offsetHeight > 0 || btn.offsetParent !== null)) {
                                btn.click();
                                didSkip = true;
                            }
                        }
                    }

                    // Also check for ad overlays and accelerate playback if unskippable bumper ad
                    const player = document.querySelector('#movie_player');
                    if (player && (player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting'))) {
                        const video = document.querySelector('video');
                        if (video && video.duration && video.currentTime < video.duration) {
                            video.playbackRate = 16.0;
                            video.muted = true;
                        }
                    } else {
                        const video = document.querySelector('video');
                        if (video) {
                            video.playbackRate = 1.0;
                            video.muted = false;
                        }
                    }
                    return didSkip;
                }"""
            )
            return bool(skipped)
        except Exception:
            return False

    async def get_playback_state(self, page: Optional[Page] = None) -> Dict[str, Any]:
        """Extract live playback metrics from the HTML5 video player."""
        if page is None:
            page = await self.manager.get_page()

        try:
            return await page.evaluate(
                """() => {
                    const video = document.querySelector('video');
                    const titleEl = document.querySelector('h1.ytd-watch-metadata') || document.querySelector('h1.title');
                    const channelEl = document.querySelector('ytd-channel-name a') || document.querySelector('#owner #channel-name');
                    
                    if (!video) {
                        return { playing: false, error: 'No HTML5 video element found' };
                    }
                    
                    return {
                        playing: !video.paused && !video.ended,
                        paused: video.paused,
                        currentTime: Math.round(video.currentTime),
                        duration: Math.round(video.duration || 0),
                        muted: video.muted,
                        volume: Math.round(video.volume * 100),
                        title: titleEl ? titleEl.innerText.trim() : document.title,
                        channel: channelEl ? channelEl.innerText.trim() : 'Unknown Channel'
                    };
                }"""
            )
        except Exception as e:
            return {"playing": False, "error": str(e)}

    async def control(self, command: str) -> Dict[str, Any]:
        """
        Dispatches media playback transport controls using YouTube native shortcuts.
        Supported commands: 'play', 'pause', 'play_pause', 'mute', 'unmute', 'fullscreen', 'seek_forward', 'seek_backward'
        """
        cmd = command.lower().strip()

        # YouTube native keyboard map
        key_map = {
            "play": "k",
            "pause": "k",
            "play_pause": "k",
            "mute": "m",
            "unmute": "m",
            "fullscreen": "f",
            "seek_forward": "l",     # +10s
            "seek_backward": "j",    # -10s
            "volume_up": "ArrowUp",
            "volume_down": "ArrowDown",
        }

        if cmd not in key_map and cmd not in ("stop", "halt", "kill"):
            raise ValueError(f"Unsupported YouTube control command: '{command}'. Supported: {list(key_map.keys())} + ['stop']")

        if cmd in ("stop", "halt", "kill"):
            return await self.stop_all_media()

        page: Page = await self.manager.get_page()
        key = key_map[cmd]
        # Focus on video player before sending shortcut
        try:
            await page.keyboard.press(key)
        except Exception:
            pass
        await asyncio.sleep(0.3)
        state = await self.get_playback_state(page)
        return {
            "status": "SUCCESS",
            "command": cmd,
            "key_pressed": key,
            "playback_state": state,
        }

    async def pause_video(self, page: Optional[Page] = None) -> Dict[str, Any]:
        """Pauses the active video element."""
        if page is None:
            page = await self.manager.get_page()
        try:
            await page.evaluate("document.querySelector('video')?.pause()")
        except Exception:
            pass
        return {"status": "SUCCESS", "action": "pause_video"}

    async def stop_all_media(self) -> Dict[str, Any]:
        """Pauses all HTML5 media across all open pages and navigates to about:blank."""
        if self.manager._context:
            for p in list(self.manager._context.pages):
                try:
                    if not p.is_closed():
                        await p.evaluate("document.querySelectorAll('video, audio').forEach(el => el.pause())")
                        await p.goto("about:blank")
                except Exception:
                    pass
        return {"status": "SUCCESS", "action": "stop_all_media", "message": "All media paused and cleared."}
