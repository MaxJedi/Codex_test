import json
import os
from typing import Any


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def ensure_data_dir(video_id: str) -> str:
    base = os.path.join("data", video_id)
    ensure_dir(base)
    return base


def get_frames_dir(video_id: str) -> str:
    """Return and ensure the persistent directory for extracted frames."""
    base = ensure_data_dir(video_id)
    frames_dir = os.path.join(base, "frames")
    ensure_dir(frames_dir)
    return frames_dir


def save_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


