import os
import shutil
import tempfile
from contextlib import contextmanager
import yt_dlp


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
        yield audio_path, video_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
