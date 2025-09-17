from fastapi import APIRouter, HTTPException

from app.schemas import Scenario, Storyboard
from app.services import make_ru_scenario, plan_timeline
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
