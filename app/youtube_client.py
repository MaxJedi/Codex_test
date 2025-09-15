import logging
import time
from typing import Any, Dict, List
import httpx
from httpx import HTTPStatusError, RequestError
from .settings import settings
from .schemas import Candidate

BASE_URL = "https://www.googleapis.com/youtube/v3"
logger = logging.getLogger(__name__)


def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params)
    params["key"] = settings.YOUTUBE_API_KEY
    backoff = 1.0
    for attempt in range(1, settings.YOUTUBE_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.get(f"{BASE_URL}{path}", params=params)
                resp.raise_for_status()
                logger.debug("YouTube API %s succeeded on attempt %s", path, attempt)
                return resp.json()
        except (HTTPStatusError, RequestError) as exc:
            logger.warning("YouTube API %s failed on attempt %s: %s", path, attempt, exc)
            if attempt == settings.YOUTUBE_MAX_RETRIES:
                raise RuntimeError(f"YouTube API request failed after {attempt} attempts") from exc
            time.sleep(backoff)
            backoff *= 2


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
        published_at = snippet.get("publishedAt")
        candidates.append(
            Candidate(
                video_id=item["id"],
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                published_at=published_at,
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                is_shorts=shorts,
            )
        )
    logger.info("Collected %s candidates for topic '%s'", len(candidates), topic)
    return candidates
