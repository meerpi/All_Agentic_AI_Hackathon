"""
Unit and Integration Tests for YouTube Data API v3 & Media Controller.
"""

from unittest.mock import MagicMock, patch
import pytest
from agent.tools.youtube_api import YouTubeAPIClient
from agent.tools.media_controller import MediaControllerTool


def test_youtube_api_create_playlist():
    yt_client = YouTubeAPIClient()
    mock_service = MagicMock()
    mock_playlists = MagicMock()
    mock_insert = MagicMock()
    mock_insert.execute.return_value = {"id": "PL_MOODY_DARK_GROOVY_123"}
    mock_playlists.insert.return_value = mock_insert
    mock_service.playlists.return_value = mock_playlists

    with patch.object(yt_client, "_get_service", return_value=mock_service):
        res = yt_client.create_playlist(
            title="Moody Dark Groovy",
            description="Autonomous curation",
            privacy_status="private"
        )
        assert res["status"] == "SUCCESS"
        assert res["playlist_id"] == "PL_MOODY_DARK_GROOVY_123"
        assert "PL_MOODY_DARK_GROOVY_123" in res["url"]


def test_youtube_api_add_tracks_to_playlist():
    yt_client = YouTubeAPIClient()
    mock_service = MagicMock()
    mock_items = MagicMock()
    mock_insert = MagicMock()
    mock_insert.execute.return_value = {"id": "item_abc_123"}
    mock_items.insert.return_value = mock_insert
    mock_service.playlistItems.return_value = mock_items

    with patch.object(yt_client, "_get_service", return_value=mock_service):
        # Pass 11-character video IDs
        res = yt_client.add_tracks_to_playlist(
            playlist_id="PL_MOODY_DARK_GROOVY_123",
            tracks=["kYJzX9a9_mE", "2S2462KmvJo"]
        )
        assert res["status"] == "SUCCESS"
        assert res["added_count"] == 2
        assert len(res["added_tracks"]) == 2


def test_youtube_api_get_liked_videos():
    yt_client = YouTubeAPIClient()
    mock_service = MagicMock()
    mock_items = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {
        "items": [
            {
                "snippet": {
                    "title": "Clandestina (JVSTIN Remix)",
                    "videoOwnerChannelTitle": "Effective Records",
                    "resourceId": {"videoId": "2S2462KmvJo"},
                    "publishedAt": "2026-08-20T10:00:00Z"
                }
            }
        ]
    }
    mock_items.list.return_value = mock_list
    mock_service.playlistItems.return_value = mock_items

    with patch.object(yt_client, "_get_service", return_value=mock_service):
        res = yt_client.get_liked_videos(max_results=10)
        assert len(res) == 1
        assert res[0]["title"] == "Clandestina (JVSTIN Remix)"
        assert res[0]["video_id"] == "2S2462KmvJo"


def test_youtube_api_search_tracks():
    yt_client = YouTubeAPIClient()
    mock_service = MagicMock()
    mock_search = MagicMock()
    mock_list = MagicMock()
    mock_list.execute.return_value = {
        "items": [
            {
                "id": {"videoId": "kYJzX9a9_mE"},
                "snippet": {
                    "title": "Lana Del Rey - Dark Paradise",
                    "channelTitle": "Lana Del Rey",
                    "description": "Official audio track"
                }
            }
        ]
    }
    mock_search.list.return_value = mock_list
    mock_service.search.return_value = mock_search

    with patch.object(yt_client, "_get_service", return_value=mock_service):
        res = yt_client.search_tracks(query="Lana Del Rey Dark Paradise", max_results=1)
        assert len(res) == 1
        assert res[0]["video_id"] == "kYJzX9a9_mE"
        assert res[0]["channel"] == "Lana Del Rey"


def test_media_controller_tool_playlist_and_liked_actions():
    tool = MediaControllerTool()
    
    # Test create_youtube_playlist routing
    with patch.object(tool.youtube_api, "create_playlist", return_value={"status": "SUCCESS", "playlist_id": "PL_TEST_999"}):
        with patch.object(tool.youtube_api, "add_tracks_to_playlist", return_value={"status": "SUCCESS", "added_count": 1}):
            res = tool.execute(
                action="create_youtube_playlist",
                title="Test Dark Wave",
                tracks=["kYJzX9a9_mE"]
            )
            assert res.success is True
            assert res.data["playlist_id"] == "PL_TEST_999"

    # Test get_liked_music routing
    with patch.object(tool.youtube_api, "get_liked_videos", return_value=[{"title": "Track 1", "video_id": "vid1"}]):
        res = tool.execute(action="get_liked_music", limit=10)
        assert res.success is True
        assert res.data["count"] == 1

    # Test youtube_transcript routing
    with patch.object(tool.youtube_api, "get_transcript", return_value={"status": "SUCCESS", "video_id": "vid1", "full_text": "Sample transcript text"}):
        res = tool.execute(action="youtube_transcript", video_id="vid1")
        assert res.success is True
        assert res.data["video_id"] == "vid1"
        assert "transcript" in res.data["full_text"]
