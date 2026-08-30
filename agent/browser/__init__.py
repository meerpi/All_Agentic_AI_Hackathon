"""
Autonomous Browser & Desktop Automation Package for Taskmaster.

Provides:
- Playwright-based persistent session management (SessionManager)
- ARIA snapshot & reference-based DOM parsing (ARIAParser)
- Multi-model vision grounding & coordinate adapters (VisionGrounding)
- Specialized YouTube driver (search, playback, ad auto-skip)
- Specialized Spotify driver (Web player & Linux MPRIS D-Bus fast-path)
- OS Desktop mouse/keyboard automation (OSDesktopDriver)
"""

from agent.browser.session_manager import BrowserSessionManager, browser_manager
from agent.browser.aria_parser import ARIAParser
from agent.browser.vision_grounding import VisionGrounding
from agent.browser.youtube_driver import YouTubeDriver
from agent.browser.spotify_driver import SpotifyDriver
from agent.browser.desktop_driver import OSDesktopDriver

__all__ = [
    "BrowserSessionManager",
    "browser_manager",
    "ARIAParser",
    "VisionGrounding",
    "YouTubeDriver",
    "SpotifyDriver",
    "OSDesktopDriver",
]
