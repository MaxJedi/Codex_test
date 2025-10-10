import os
import tempfile
from typing import Optional

import httpx
import subprocess
from urllib.parse import urlsplit, urlunsplit

from app.core.settings import settings
import logging
from app.integrations.yt_dlp import YtDlpDownloader

logger = logging.getLogger(__name__)

def _build_payload(video_url: str) -> dict:
    video_quality = os.getenv("COBALT_VIDEO_QUALITY", settings.__dict__.get("COBALT_VIDEO_QUALITY", "720"))
    payload = {
        "url": video_url,
        "videoQuality": video_quality,
        "audioFormat": "mp3",
        "filenameStyle": "basic",
        "alwaysProxy": True,
    }
    return payload


def _ensure_data_dir() -> str:
    data_dir = os.path.join("data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _stream_download(client: httpx.Client, url: str, dest_path: str) -> None:
    with client.stream("GET", url, timeout=120) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if content_type.startswith("application/json") or content_type.startswith("text/"):
            # Prevent saving JSON or HTML error into mp4
            body = r.read().decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"Cobalt download returned non-binary content-type {content_type}: {body}")
        _ensure_data_dir()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_bytes():
                if chunk:
                    f.write(chunk)


def _download_with_cobalt(video_url: str, client: Optional[httpx.Client] = None) -> tuple[str | None, str | None]:
    base_url = settings.__dict__.get("COBALT_BASE_URL")
    if not base_url:
        raise RuntimeError("COBALT_BASE_URL is not set")

    client = client or httpx.Client(timeout=60)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = _build_payload(video_url)
    resp = client.post(base_url, json=payload, headers=headers)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        raise RuntimeError(f"Cobalt HTTP error {resp.status_code}: {body}") from exc
    _ = tempfile.mkdtemp()
    audio_path = video_path = None
    # Case 1: JSON envelope with links

    data = resp.json()
    video_link = data.get("url")
    # Allow overriding the host for the downloadable link if needed
    override_base = os.getenv("COBALT_DOWNLOAD_HOST")  # e.g. http://cobalt-api:9000 or http://localhost:9000
    if video_link and override_base:
        try:
            parts = urlsplit(video_link)
            base_parts = urlsplit(override_base)
            new_parts = (
                base_parts.scheme or parts.scheme,
                base_parts.netloc or parts.netloc,
                parts.path,
                parts.query,
                parts.fragment,
            )
            video_link = urlunsplit(new_parts)
        except Exception:
            pass
    if video_link:
        logger.info(f"Video link: {video_link}")
        video_path = os.path.join(_ensure_data_dir(), "video.mp4")
        _stream_download(client, video_link, video_path)
        logger.info(f"Video saved to {video_path}")


    return audio_path, video_path



def pull_transient(video_id: str, max_seconds: int = 90):
    """Fetch audio/video via Cobalt and yield temp file paths, then clean up.

    Mirrors app.media_probe.pull_transient interface.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    yt_dlp = YtDlpDownloader()
    download_result = yt_dlp.download(url)
    video_path = download_result.filepath


    extracted_audio = os.path.join(_ensure_data_dir(), "audio.mp3")
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        "0",
        "-t",
        str(max_seconds),
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        extracted_audio,
    ]
    if not video_path or not os.path.exists(video_path) or os.path.getsize(video_path) < 1024 * 100:
        raise RuntimeError(f"Downloaded video seems invalid or too small: {video_path}")
    res = subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"FFmpeg command result: {res}")
    audio_path = extracted_audio if os.path.exists(extracted_audio) else None

    return audio_path, video_path


