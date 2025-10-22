from fastapi import APIRouter, HTTPException
import os

from app.schemas import AnalysisResult
from app.services import transcribe, detect_shots, ensure_data_dir, save_json, concatenate_videos_in_dir
from app.integrations import cobalt
from app.integrations.yt_dlp import YtDlpDownloader
from app.core.settings import settings
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/analyze", response_model=AnalysisResult)
def analyze(payload: dict) -> AnalysisResult:
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id required")
    
    audio_path, video_path = cobalt.pull_transient(video_id)
    print(f"Audio path: {audio_path}")
    print(f"Video path: {video_path}")
    if not audio_path:
        raise HTTPException(500, "Audio not extracted")
    
    transcript = transcribe(audio_path)
    # persist transcript
    out_dir = ensure_data_dir(video_id)
    save_json(os.path.join(out_dir, "transcript.json"), transcript.model_dump())
    
    if video_path:
        shots, key_objects = detect_shots(video_path, video_id)
    else:
        shots, key_objects = [], []
    
    # persist vision
    save_json(os.path.join(out_dir, "vision.json"), {
        "shots": [s.model_dump() for s in shots],
        "key_objects": [k.model_dump() for k in key_objects],
    })
    
    return AnalysisResult(transcript=transcript, shots=shots, key_objects=key_objects)


@router.post("/download")
def download(payload: dict) -> dict:
    url = payload.get("url")
    if not url:
        raise HTTPException(400, "url required")
    filename = payload.get("filename")
    quality = payload.get("quality", "best[ext=mp4]/best")
    dl = YtDlpDownloader(download_dir="data")
    try:
        res = dl.download(url, quality=quality, filename=filename)
    except Exception as e:
        raise HTTPException(500, f"Download failed: {e}")
    return {"video_id": res.video_id, "title": res.title, "filepath": res.filepath}


@router.post("/concatenate")
def concatenate(payload: dict) -> dict:
    input_dir = payload.get("input_dir")
    video_id = payload.get("video_id")
    pattern = payload.get("pattern") or "series_shot_*.mp4"
    output_name = payload.get("output_name") or "merged.mp4"

    if not input_dir and not video_id:
        raise HTTPException(400, "input_dir or video_id required")

    if not input_dir and video_id:
        base_dir = settings.DATA_DIR
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        input_dir = os.path.join(app_dir, base_dir, settings.VIDEO_SHOTS_DIRNAME)
    logger.info(f"Concatenating videos in directory: {input_dir}")
    try:
        output_path = concatenate_videos_in_dir(input_dir, pattern=pattern, output_name=output_name)
    except Exception as e:
        raise HTTPException(500, f"Concatenation failed: {e}")

    return {"input_dir": input_dir, "output": output_path}
