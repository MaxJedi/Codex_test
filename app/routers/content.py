from fastapi import APIRouter, HTTPException

from app.schemas.content import Scenario, Storyboard, GeneratedVideo
from app.services import make_ru_scenario, plan_timeline, RunwayVideoService
from app.routers.media import analyze
from app.schemas import Transcript, Shot, KeyObject
from app.services.storage_service import read_json
import os

router = APIRouter(prefix="/content", tags=["content"])


@router.post("/scenario", response_model=Scenario)
def scenario(payload: dict):
    video_id = payload.get("video_id")
    topic = payload.get("topic")
    if not video_id or not topic:
        raise HTTPException(400, "video_id and topic required")
    
    analysis = analyze({"video_id": video_id})
    transcript = analysis.transcript
    shots = analysis.shots
    key_objects = analysis.key_objects
    return make_ru_scenario(transcript, shots, topic, key_objects)

@router.post("/storyboard", response_model=Storyboard)
def storyboard(payload: dict):
    scenario_data = payload.get("scenario")
    target = payload.get("target")
    if not scenario_data or not target:
        raise HTTPException(400, "scenario and target required")
    
    scn = Scenario.model_validate(scenario_data)
    return plan_timeline(scn, target)


@router.post("/video", response_model=GeneratedVideo)
def generate_video(payload: dict) -> GeneratedVideo:
    scenario_data = payload.get("scenario")
    # duration = int(payload.get("duration", 5))
    ratio = payload.get("ratio", "1280:720")
    # if not scenario_data:
    #     raise HTTPException(400, "scenario required")

    # scn = Scenario.model_validate(scenario_data)
    svc = RunwayVideoService()
    result = svc.generate_from_text(scenario_data, duration=8, ratio=ratio)
    return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)


@router.post("/scenario_cached", response_model=Scenario)
def scenario_cached(payload: dict):
    """Generate scenario using existing cached analysis files in data/<video_id>.

    Expects payload: {"video_id": str, "topic": str}
    """
    video_id = payload.get("video_id")
    topic = payload.get("topic")
    if not video_id or not topic:
        raise HTTPException(400, "video_id and topic required")

    base_dir = os.path.join("data", video_id)
    transcript_path = os.path.join(base_dir, "transcript.json")
    vision_path = os.path.join(base_dir, "vision.json")
    if not os.path.exists(transcript_path):
        raise HTTPException(404, f"transcript not found for {video_id}")
    if not os.path.exists(vision_path):
        raise HTTPException(404, f"vision not found for {video_id}")

    t_raw = read_json(transcript_path)
    v_raw = read_json(vision_path)

    # Build models
    segments = [
        {"text": s.get("text", ""), "start": float(s.get("start", 0)), "end": float(s.get("end", 0))}
        for s in t_raw.get("segments", t_raw if isinstance(t_raw, list) else [])
    ]
    transcript = Transcript.model_validate({"segments": segments})

    shots = [
        Shot(start_sec=float(s.get("start_sec", s.get("start", 0.0))), end_sec=float(s.get("end_sec", s.get("end", 0.0))))
        for s in v_raw.get("shots", [])
    ]
    key_objects = [
        KeyObject(
            description=str(o.get("description", "")),
            start_sec=float(o.get("start_sec", o.get("start", 0.0))),
            end_sec=float(o.get("end_sec", o.get("end", 0.0))),
            confidence=(float(o["confidence"]) if o.get("confidence") is not None else None),
            categories=list(o.get("categories", []) or []),
        )
        for o in v_raw.get("key_objects", [])
    ]

    return make_ru_scenario(transcript, shots, topic, key_objects)
