import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
import yt_dlp
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)


@contextmanager
def pull_transient(video_id: str, max_seconds: int = 90):
    tmpdir = tempfile.mkdtemp()
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = os.path.join(tmpdir, f"%(id)s.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "outtmpl": outtmpl,
        "format": "mp4/bestaudio[ext=m4a]",
        "postprocessor_args": ["-ss", "0", "-t", str(max_seconds)],
        "concurrent_fragment_downloads": 1,
        "nocheckcertificate": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        files = os.listdir(tmpdir)
        audio_path = video_path = None
        for fname in files:
            if fname.endswith(".m4a"):
                audio_path = os.path.join(tmpdir, fname)
            elif fname.endswith(".mp4"):
                video_path = os.path.join(tmpdir, fname)
        if not audio_path:
            raise RuntimeError("Audio stream could not be extracted")
        logger.debug("Transient media ready at %s (audio=%s, video=%s)", tmpdir, bool(audio_path), bool(video_path))
        yield audio_path, video_path
    except DownloadError as exc:
        logger.error("yt-dlp failed for %s: %s", video_id, exc)
        raise RuntimeError(f"Failed to download media for video {video_id}") from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
