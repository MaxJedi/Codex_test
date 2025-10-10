import argparse
import json
import sys

from app.integrations.yt_dlp import YtDlpDownloader


def main() -> int:
    parser = argparse.ArgumentParser(description="Test yt-dlp download")
    parser.add_argument("url", help="Video URL to download")
    parser.add_argument("--quality", default="best[ext=mp4]/best")
    args = parser.parse_args()

    dl = YtDlpDownloader(download_dir="data")
    res = dl.download(args.url, quality=args.quality)
    print(json.dumps({
        "video_id": res.video_id,
        "title": res.title,
        "filepath": res.filepath,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


