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


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _extract_frames(file_path: str, fps: int, max_frames: int) -> List[str]:
    tmpdir = tempfile.mkdtemp(prefix="frames_")
    try:
        pattern = os.path.join(tmpdir, "frame_%05d.jpg")
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
        frame_files = sorted(glob.glob(os.path.join(tmpdir, "frame_*.jpg")))[:max_frames]
        return [_encode_image(p) for p in frame_files]
    finally:
        # temp frames dir will be cleaned by caller if needed; keep for safety on errors
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


def detect_shots(file_path: str) -> Tuple[List[Shot], List[KeyObject]]:
    fps = getattr(settings, "VISION_FRAME_FPS", 1)
    max_frames = getattr(settings, "VISION_MAX_FRAMES", 75)
    model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4.1-mini")

    base64_frames = _extract_frames(file_path, fps=fps, max_frames=max_frames)

    system_prompt = (
        "Analyze provided video frames. Return STRICT JSON with keys 'shots' and 'key_objects'. \n"
        "shots: list of objects: {start_sec: number, end_sec: number}. \n"
        "key_objects: list of objects: {description: string, start_sec: number, end_sec: number, confidence: number (0..1), categories: string[]}\n"
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

