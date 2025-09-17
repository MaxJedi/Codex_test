from app import youtube_client


def test_search_trending(monkeypatch):
    def fake_search_list(**params):
        return {"items": [{"id": {"videoId": "abc"}}]}

    def fake_videos_list(**params):
        return {
            "items": [
                {
                    "id": "abc",
                    "snippet": {
                        "title": "T",
                        "channelTitle": "C",
                        "publishedAt": "2025-08-02T00:00:00Z",
                    },
                    "statistics": {"viewCount": "10", "likeCount": "1"},
                }
            ]
        }

    monkeypatch.setattr(youtube_client, "search_list", fake_search_list)
    monkeypatch.setattr(youtube_client, "videos_list", fake_videos_list)
    res = youtube_client.search_trending("test", 1, "RU", "2025-08-01T00:00:00Z")
    assert res[0].video_id == "abc"
    assert res[0].view_count == 10
