import httpx
from typing import Any, Dict, List
from .settings import settings
from .schemas import Candidate

BASE_URL = "https://www.googleapis.com/youtube/v3"


def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params)
    params["key"] = settings.YOUTUBE_API_KEY
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


def search_list(**params) -> Dict[str, Any]:
    return _request("/search", params)


def videos_list(**params) -> Dict[str, Any]:
    return _request("/videos", params)


def search_trending(topic: str, n: int, region: str, published_after: str, shorts: bool = True) -> List[Candidate]:
    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "q": topic,
        "publishedAfter": published_after,
        "regionCode": region,
        "maxResults": min(max(n, 5), 50),
    }
    if shorts:
        params["videoDuration"] = "short"
    search_resp = search_list(**params)
    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])][:n]
    if not video_ids:
        return []
    videos_resp = videos_list(part="snippet,contentDetails,statistics", id=",".join(video_ids))
    candidates: List[Candidate] = []
    for item in videos_resp.get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        candidates.append(
            Candidate(
                video_id=item["id"],
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                published_at=snippet.get("publishedAt"),
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                is_shorts=shorts,
            )
        )
    return candidates
