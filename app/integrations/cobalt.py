import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Optional

import httpx
import subprocess

from app.core.settings import settings
import logging

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


def _download_with_cobalt(video_url: str, client: Optional[httpx.Client] = None) -> tuple[str | None, str | None]:
    base_url = settings.__dict__.get("COBALT_BASE_URL")
    if not base_url:
        raise RuntimeError("COBALT_BASE_URL is not set")

    own_client = client is None
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
    tmpdir = tempfile.mkdtemp()
    audio_path = video_path = None
    # Case 1: JSON envelope with links

    data = resp.json()
    video_link = data.get("url")
    video_link = video_link.replace("cobalt-api", "localhost")
    if video_link:
        logger.info(f"Video link: {video_link}")
        video_bin = client.get(video_link)
        video_bin.raise_for_status()
        video_path = os.path.join("data", "video.mp4")
        with open(video_path, "wb") as f:
            f.write(video_bin.content)
            logger.info(f"Video saved to {video_path}")


    return audio_path, video_path



def pull_transient(video_id: str, max_seconds: int = 90):
    """Fetch audio/video via Cobalt and yield temp file paths, then clean up.

    Mirrors app.media_probe.pull_transient interface.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    audio_path = video_path = None
    tmp_root: Optional[str] = None
    audio_path, video_path = _download_with_cobalt(url)
    tmp_root = os.path.dirname(audio_path or video_path or tempfile.mkdtemp())


    extracted_audio = os.path.join("data", "audio.mp3")
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
    res = subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"FFmpeg command result: {res}")
    audio_path = extracted_audio if os.path.exists(extracted_audio) else None

    return audio_path, video_path


