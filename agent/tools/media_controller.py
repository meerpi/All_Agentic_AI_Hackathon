"""
Autonomous Media Controller Tool for Taskmaster (YouTube & Spotify).

Provides:
- YouTube autonomous video search, playback, ad auto-skipping, and transport controls
- Spotify Web Player search, playlist creation, and Linux MPRIS fast-path controls
"""

import logging
from typing import Any, Dict, Optional
from agent.browser.session_manager import browser_manager
from agent.browser.spotify_driver import SpotifyDriver
from agent.browser.youtube_driver import YouTubeDriver
from agent.tools.base import BaseTool
from agent.tools.youtube_api import youtube_api_client

logger = logging.getLogger("taskmaster.tools.media")


class MediaControllerTool(BaseTool):
    name = "media_controller"
    description = (
        "Autonomous Media & Music Controller for YouTube & Spotify. "
        "Actions: create_youtube_playlist, youtube_api_search, get_liked_music, youtube_play, youtube_control, youtube_status, "
        "spotify_play, spotify_create_playlist, spotify_control."
    )

    def __init__(self):
        self.manager = browser_manager
        self.youtube = YouTubeDriver()
        self.spotify = SpotifyDriver()
        self.youtube_api = youtube_api_client

    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """Synchronous entrypoint called by Taskmaster DAG orchestrator."""
        act = action.lower().strip()

        # ── Official YouTube Data API v3 Fast-Path (No browser overhead) ──
        if act in ("create_youtube_playlist", "youtube_create_playlist"):
            title = kwargs.get("title") or kwargs.get("playlist_name") or "Taskmaster Playlist"
            desc = kwargs.get("description", "Curated autonomously by Taskmaster Agent")
            privacy = kwargs.get("privacy", "private")
            tracks = kwargs.get("tracks") or kwargs.get("songs") or []

            pl_res = self.youtube_api.create_playlist(title=title, description=desc, privacy_status=privacy)
            if tracks and pl_res.get("playlist_id"):
                add_res = self.youtube_api.add_tracks_to_playlist(pl_res["playlist_id"], tracks)
                pl_res["tracks_added"] = add_res
            return pl_res

        elif act in ("get_liked_music", "youtube_liked_videos", "get_liked_videos"):
            limit = int(kwargs.get("limit", 50))
            liked = self.youtube_api.get_liked_videos(max_results=limit)
            return {"status": "SUCCESS", "count": len(liked), "liked_videos": liked}

        elif act in ("youtube_api_search", "search_youtube_api"):
            query = kwargs.get("query") or kwargs.get("search_query")
            limit = int(kwargs.get("limit", 5))
            results = self.youtube_api.search_tracks(query=query, max_results=limit)
            return {"status": "SUCCESS", "query": query, "results": results}

        # ── Browser-based Playback Actions (Headless or Headed) ────────
        duration = kwargs.get("duration_seconds") or kwargs.get("duration") or kwargs.get("play_duration_seconds")
        timeout = (float(duration) + 45.0) if duration else None
        return self.manager.run_sync(self._run_async(action, **kwargs), timeout=timeout)

    async def _run_async(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        act = action.lower().strip()

        # ── YouTube Playback Operations ────────────────────────────────
        if act in ("youtube_play", "youtube_search", "play_youtube", "search_youtube"):
            url = kwargs.get("url") or kwargs.get("video_url")
            seek_seconds = kwargs.get("seek_seconds") or kwargs.get("seek") or kwargs.get("t")
            duration = kwargs.get("duration_seconds") or kwargs.get("duration") or kwargs.get("play_duration_seconds")
            auto_close = bool(kwargs.get("auto_close", False) or kwargs.get("close_after", False))
            if url:
                return await self.youtube.play_video(url=url, seek_seconds=seek_seconds)
            query = kwargs.get("query") or kwargs.get("search_query") or kwargs.get("title")
            if not query:
                raise ValueError("YouTube action requires parameter 'query' or 'url'.")
            return await self.youtube.search_and_play(
                query=query,
                duration_seconds=int(duration) if duration else None,
                auto_close=auto_close
            )

        elif act in ("youtube_control", "youtube_transport"):
            cmd = kwargs.get("command") or kwargs.get("playback_command") or "play_pause"
            return await self.youtube.control(command=cmd)

        elif act in ("youtube_status", "get_youtube_status"):
            page = await self.manager.get_page()
            state = await self.youtube.get_playback_state(page)
            return {"status": "SUCCESS", "playback_state": state, "url": page.url}

        # ── Spotify Operations ─────────────────────────────────────────
        elif act in ("spotify_play", "spotify_search", "play_spotify", "search_spotify"):
            query = kwargs.get("query") or kwargs.get("track") or kwargs.get("artist") or kwargs.get("album")
            if not query:
                raise ValueError("Spotify search action requires parameter 'query'.")
            return await self.spotify.search_and_play(query=query)

        elif act in ("spotify_create_playlist", "create_spotify_playlist"):
            name = kwargs.get("name") or kwargs.get("playlist_name") or "Taskmaster Playlist"
            description = kwargs.get("description")
            return await self.spotify.create_playlist(name=name, description=description)

        elif act in ("spotify_control", "spotify_transport"):
            cmd = kwargs.get("command") or kwargs.get("playback_command") or "play_pause"
            return await self.spotify.control(command=cmd)

        else:
            raise ValueError(
                f"Unknown media action: '{action}'. Supported actions: "
                "['create_youtube_playlist', 'get_liked_music', 'youtube_api_search', 'youtube_play', 'youtube_control', 'youtube_status', 'spotify_play', 'spotify_create_playlist', 'spotify_control']"
            )
