from fastapi import APIRouter, HTTPException
import json
import os

from app.schemas import AnalysisResult
from app.services import transcribe, detect_shots, ensure_data_dir, save_json
from app.integrations import cobalt

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
        shots, key_objects = detect_shots(video_path)
    else:
        shots, key_objects = [], []
    
    # persist vision
    save_json(os.path.join(out_dir, "vision.json"), {
        "shots": [s.model_dump() for s in shots],
        "key_objects": [k.model_dump() for k in key_objects],
    })
    
    return AnalysisResult(transcript=transcript, shots=shots, key_objects=key_objects)
