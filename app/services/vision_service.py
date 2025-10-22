import base64
import glob
import subprocess
import tempfile
import os
from typing import Tuple, List

import httpx
from openai import OpenAI
import shutil

from app.schemas import Shot, KeyObject
from app.core.settings import settings
from app.services.storage_service import get_frames_dir, ensure_dir


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _extract_frames(
    file_path: str,
    fps: int,
    max_frames: int,
    dest_dir: str | None = None,
) -> Tuple[List[str], List[str]]:
    """Extract frames with ffmpeg.

    If dest_dir is provided, frames are written there as frame_00001.jpg etc and kept.
    Returns (base64_frames, saved_paths). If dest_dir is None, frames are extracted
    in a temporary directory and then removed; saved_paths will be empty.
    """
    
    if not dest_dir:
        dest_dir = os.path.join(settings.DATA_DIR, settings.FRAMES_DIR)
        ensure_dir(dest_dir)
    if dest_dir:
        pattern = os.path.join(dest_dir, "frame_%05d.jpg")
        tmpdir = None
    else:
        tmpdir = tempfile.mkdtemp(prefix="frames_")
        pattern = os.path.join(tmpdir, "frame_%05d.jpg")
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-vf",
            f"fps={fps}",
            "-q:v",
            "2",
            pattern,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        search_dir = dest_dir or tmpdir or "."
        all_frames = sorted(glob.glob(os.path.join(search_dir, "frame_*.jpg")))
        frame_files = all_frames[:max_frames]
        base64_frames = [_encode_image(p) for p in frame_files]
        saved_paths = frame_files if dest_dir else []
        # If we created extra frames beyond max_frames in a persistent dir, clean extras
        if dest_dir and len(all_frames) > len(frame_files):
            for extra in all_frames[len(frame_files):]:
                try:
                    os.remove(extra)
                except Exception:
                    pass
        return base64_frames, saved_paths
    finally:
        if tmpdir:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


_vision_client: OpenAI | None = None


def _get_vision_client() -> OpenAI:
    global _vision_client
    if _vision_client is None:
        proxies = {}
        http_proxy = getattr(settings, "OPENAI_HTTP_PROXY", None)
        https_proxy = getattr(settings, "OPENAI_HTTPS_PROXY", None)
        if http_proxy:
            proxies["http://"] = http_proxy
        if https_proxy:
            proxies["https://"] = https_proxy
        timeout = httpx.Timeout(getattr(settings, "OPENAI_TIMEOUT_SECONDS", 120))
        http_client = httpx.Client(proxies=proxies or None, timeout=timeout)
        _vision_client = OpenAI(api_key=settings.OPENAI_API_KEY, http_client=http_client,
                                max_retries=getattr(settings, "OPENAI_MAX_RETRIES", 2))
    return _vision_client


def detect_shots(file_path: str, video_id: str | None = None) -> Tuple[List[Shot], List[KeyObject]]:
    fps = getattr(settings, "VISION_FRAME_FPS", 1)
    max_frames = getattr(settings, "VISION_MAX_FRAMES", 75)
    model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4.1-mini")

    dest_dir = get_frames_dir(video_id) if video_id else None
    base64_frames, _saved_paths = _extract_frames(file_path, fps=fps, max_frames=max_frames, dest_dir=dest_dir)

    system_prompt = (
        "Analyze provided video frames. Return STRICT JSON with keys 'shots' and 'key_objects'. \n"
        "shots: list of objects: {start_sec: number, end_sec: number}. \n"
        "key_objects: list of objects: {description: string, start_sec: number, end_sec: number, confidence: number (0..1), categories: string[]}. \n"
        "In 'key_objects', include any prominently featured objects, characters (with notable expressions), or important background elements. Use descriptive labels and appropriate categories (e.g., 'person', 'animal', 'vehicle', 'environment'). \n"
        "Estimate timestamps based on frame index and fps=" + str(fps) + ". If unsure, keep empty lists."
    )
    # Build chat-completions with vision
    message_content = [{"type": "text", "text": system_prompt}]
    step = max(1, len(base64_frames) // max(1, min(len(base64_frames), max_frames)))
    for frame in base64_frames[::step]:
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame}"},
        })

    client = _get_vision_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message_content}],
        temperature=0,
        response_format={"type": "json_object"},
        timeout=getattr(settings, "OPENAI_TIMEOUT_SECONDS", 120),
    )
    text = resp.choices[0].message.content if resp and resp.choices else ""
    import json
    data = json.loads(text) if text else {}
    shots = [Shot(start_sec=float(s.get("start_sec", 0.0)), end_sec=float(s.get("end_sec", 0.0))) for s in data.get("shots", [])]
    key_objects = [
        KeyObject(
            description=str(o.get("description", "")),
            start_sec=float(o.get("start_sec", 0.0)),
            end_sec=float(o.get("end_sec", 0.0)),
            confidence=float(o.get("confidence", 0.0)) if o.get("confidence") is not None else None,
            categories=list(o.get("categories", []) or []),
        )
        for o in data.get("key_objects", [])
    ]
    
    return shots, key_objects


