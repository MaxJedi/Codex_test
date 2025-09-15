import logging
import os
import time
from typing import Any, Dict, List

import httpx

from .settings import settings
from .schemas import Candidate

BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeAPIRequestError(RuntimeError):
    """Raised when the YouTube API repeatedly fails."""


_LOG_LEVEL_NAME = os.getenv("YOUTUBE_CLIENT_LOG_LEVEL", "INFO").upper()
_ENV_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, None)
_INVALID_LOG_LEVEL = not isinstance(_ENV_LOG_LEVEL, int)
_LOG_LEVEL = _ENV_LOG_LEVEL if not _INVALID_LOG_LEVEL else logging.INFO

if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=_LOG_LEVEL)

logger = logging.getLogger(__name__)
logger.setLevel(_LOG_LEVEL)

if _INVALID_LOG_LEVEL:
    logger.warning(
        "Invalid log level '%s' provided for YOUTUBE_CLIENT_LOG_LEVEL. Defaulting to INFO.",
        _LOG_LEVEL_NAME,
    )


def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params)
    params["key"] = settings.YOUTUBE_API_KEY
    sanitized_params = {k: v for k, v in params.items() if k != "key"}

    max_attempts = 3
    backoff_seconds = 1.0
    last_exception: Exception | None = None

    with httpx.Client(timeout=30) as client:
        for attempt in range(1, max_attempts + 1):
            logger.info(
                "Requesting %s with params %s (attempt %s/%s)",
                path,
                sanitized_params,
                attempt,
                max_attempts,
            )
            try:
                resp = client.get(f"{BASE_URL}{path}", params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_exception = exc
                logger.warning(
                    "Request to %s failed on attempt %s/%s: %s",
                    path,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt < max_attempts:
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2

    logger.error(
        "Request to %s exhausted %s attempts with params %s.",
        path,
        max_attempts,
        sanitized_params,
    )
    raise YouTubeAPIRequestError(
        f"Failed to call YouTube API endpoint '{path}' after {max_attempts} attempts."
    ) from last_exception


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
