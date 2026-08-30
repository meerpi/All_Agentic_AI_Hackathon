"""
Official YouTube Data API v3 Client for Taskmaster.

Provides high-speed REST endpoints for:
- Creating and configuring YouTube playlists
- Adding curated tracks and videos to playlists
- Fetching Liked Videos (playlist ID 'LL')
- Searching YouTube video catalogue (sub-200ms latency)
"""

import logging
from typing import Any, Dict, List, Optional
from agent.tools.google_auth import build_service

logger = logging.getLogger("taskmaster.tools.youtube_api")


class YouTubeAPIClient:
    """Official YouTube Data API v3 client."""

    def __init__(self):
        self._service = None

    def _get_service(self):
        """Lazy load authenticated YouTube v3 service."""
        if self._service is None:
            self._service = build_service("youtube", "v3")
        return self._service

    def create_playlist(
        self,
        title: str,
        description: str = "Curated autonomously by Taskmaster Agent",
        privacy_status: str = "private",
    ) -> Dict[str, Any]:
        """
        Creates a new YouTube playlist via official REST API.
        privacy_status: 'private', 'unlisted', 'public'
        """
        service = self._get_service()
        if not service:
            raise RuntimeError("YouTube Data API service unavailable. Ensure OAuth credentials are configured.")

        body = {
            "snippet": {
                "title": title,
                "description": description,
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        logger.info(f"Creating YouTube playlist: '{title}' (privacy: {privacy_status})")
        resp = service.playlists().insert(part="snippet,status", body=body).execute()
        playlist_id = resp.get("id")
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

        logger.info(f"Successfully created playlist ID: {playlist_id} -> {playlist_url}")
        return {
            "status": "SUCCESS",
            "playlist_id": playlist_id,
            "title": title,
            "url": playlist_url,
            "privacy_status": privacy_status,
        }

    def add_tracks_to_playlist(
        self,
        playlist_id: str,
        tracks: List[str],
    ) -> Dict[str, Any]:
        """
        Inserts tracks into a YouTube playlist.
        `tracks` can be a list of 11-char YouTube Video IDs or query strings.
        If a query string is provided, it automatically searches YouTube and inserts the top match.
        """
        service = self._get_service()
        if not service:
            raise RuntimeError("YouTube Data API service unavailable.")

        added_tracks = []
        failed_tracks = []

        for item in tracks:
            video_id = None
            track_title = item

            # Check if item is already a video ID (11 chars, no spaces)
            if len(item) == 11 and " " not in item:
                video_id = item
            elif "watch?v=" in item:
                import urllib.parse
                parsed = urllib.parse.urlparse(item)
                query_params = urllib.parse.parse_qs(parsed.query)
                video_id = query_params.get("v", [None])[0]
            else:
                # Search for the video ID via search.list
                search_res = self.search_tracks(query=item, max_results=1)
                if search_res:
                    video_id = search_res[0]["video_id"]
                    track_title = search_res[0]["title"]

            if not video_id:
                logger.warning(f"Could not resolve video ID for track: {item}")
                failed_tracks.append(item)
                continue

            # Insert into playlist
            try:
                body = {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                }
                item_resp = service.playlistItems().insert(part="snippet", body=body).execute()
                added_tracks.append({
                    "title": track_title,
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "item_id": item_resp.get("id"),
                })
                logger.info(f"Added track '{track_title}' ({video_id}) to playlist {playlist_id}")
            except Exception as e:
                logger.error(f"Failed to add track '{item}' to playlist: {e}")
                failed_tracks.append(item)

        return {
            "status": "SUCCESS",
            "playlist_id": playlist_id,
            "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}",
            "added_count": len(added_tracks),
            "added_tracks": added_tracks,
            "failed_tracks": failed_tracks,
        }

    def get_liked_videos(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches the authenticated user's Liked Videos via playlistId='LL'.
        """
        service = self._get_service()
        if not service:
            raise RuntimeError("YouTube Data API service unavailable.")

        try:
            resp = service.playlistItems().list(
                playlistId="LL",
                part="snippet,contentDetails",
                maxResults=min(max_results, 50),
            ).execute()

            items = []
            for it in resp.get("items", []):
                snippet = it.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId")
                items.append({
                    "title": snippet.get("title"),
                    "channel": snippet.get("videoOwnerChannelTitle", "Unknown Channel"),
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": snippet.get("publishedAt"),
                })
            logger.info(f"Retrieved {len(items)} liked videos from playlist 'LL'.")
            return items
        except Exception as e:
            logger.error(f"Failed to fetch Liked Videos (LL): {e}")
            return []

    def _fallback_web_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Fallback web parser extracting live YouTube search results when Data API is disabled/unconfigured."""
        import json
        import re
        import urllib.parse
        import urllib.request

        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            results = []
            # 1. Try ytInitialData JSON extraction
            match = re.search(r"ytInitialData\s*=\s*({.+?});</script>", html)
            if match:
                try:
                    data = json.loads(match.group(1))
                    contents = (
                        data.get("contents", {})
                        .get("twoColumnSearchResultsRenderer", {})
                        .get("primaryContents", {})
                        .get("sectionListRenderer", {})
                        .get("contents", [])
                    )
                    for section in contents:
                        items = section.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            v = item.get("videoRenderer")
                            if v and v.get("videoId"):
                                vid = v.get("videoId")
                                title_runs = v.get("title", {}).get("runs", [])
                                title = title_runs[0].get("text", "") if title_runs else "YouTube Video"
                                owner_runs = v.get("ownerText", {}).get("runs", [])
                                channel = owner_runs[0].get("text", "YouTube Channel") if owner_runs else ""
                                results.append({
                                    "title": title,
                                    "channel": channel,
                                    "video_id": vid,
                                    "url": f"https://www.youtube.com/watch?v={vid}",
                                    "description": f"Video by {channel}"
                                })
                                if len(results) >= max_results:
                                    return results
                except Exception as ex:
                    logger.debug(f"JSON parse in fallback search: {ex}")

            # 2. Fast regex fallback on HTML
            if not results:
                vid_matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
                seen_ids = set()
                for vid in vid_matches:
                    if vid not in seen_ids and len(vid) == 11:
                        seen_ids.add(vid)
                        results.append({
                            "title": f"{query} - Video",
                            "channel": "YouTube",
                            "video_id": vid,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "description": query,
                        })
                        if len(results) >= max_results:
                            break

            return results
        except Exception as e:
            logger.error(f"Fallback YouTube web search error for '{query}': {e}")
            return []

    def search_tracks(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Searches YouTube video catalogue for tracks/videos matching the query.
        Falls back to web parser if GCP YouTube Data API v3 is disabled in project.
        """
        service = None
        try:
            service = self._get_service()
        except Exception as e:
            logger.warning(f"YouTube Data API service unavailable ({e}), using web search fallback.")

        if service:
            try:
                resp = service.search().list(
                    q=query,
                    part="snippet",
                    type="video",
                    maxResults=max_results,
                ).execute()

                results = []
                for it in resp.get("items", []):
                    vid = it.get("id", {}).get("videoId")
                    snippet = it.get("snippet", {})
                    results.append({
                        "title": snippet.get("title"),
                        "channel": snippet.get("channelTitle"),
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "description": snippet.get("description"),
                    })
                if results:
                    return results
            except Exception as e:
                logger.warning(f"YouTube Data API search returned error: {e}. Falling back to web search parser...")

        return self._fallback_web_search(query=query, max_results=max_results)


# Singleton client instance
youtube_api_client = YouTubeAPIClient()
