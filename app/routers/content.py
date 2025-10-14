from fastapi import APIRouter, HTTPException

from app.schemas.content import Scenario, Storyboard, GeneratedVideo
from app.services import make_ru_scenario, plan_timeline, RunwayVideoService
from app.routers.media import analyze

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
    duration = int(payload.get("duration", 5))
    ratio = payload.get("ratio", "1280:720")
    if not scenario_data:
        raise HTTPException(400, "scenario required")

    scn = Scenario.model_validate(scenario_data)
    svc = RunwayVideoService()
    result = svc.generate_from_text(scn, duration=8, ratio=ratio)
    return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)
