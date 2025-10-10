import os
from typing import Any

from pydantic import BaseModel
from yt_dlp import YoutubeDL


class YtDlpResult(BaseModel):
    video_id: str | None = None
    title: str | None = None
    filepath: str | None = None
    info: dict[str, Any] = {}


class YtDlpDownloader:
    def __init__(self, download_dir: str = "data") -> None:
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    def download(self, url: str, *, quality: str = "best[ext=mp4]/best", filename: str | None = None) -> YtDlpResult:
        outtmpl = os.path.join(self.download_dir, filename or "%(id)s.%(ext)s")
        ydl_opts = {
            "format": quality,
            "outtmpl": outtmpl,
            "noprogress": True,
            "quiet": True,
            "nocheckcertificate": True,
            # Useful general options from yt-dlp docs
            # https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#general-options
            "retries": 3,
            "fragment_retries": 3,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Compute saved path
            if "requested_downloads" in info and info["requested_downloads"]:
                filepath = info["requested_downloads"][0].get("_filename")
            else:
                filepath = ydl.prepare_filename(info)

        return YtDlpResult(
            video_id=info.get("id"),
            title=info.get("title"),
            filepath=filepath,
            info=info,
        )


