import logging
from typing import Literal, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from . import youtube_client, media_probe, stt, vision_shots, llm_scenario, llm_storyboard
from .schemas import Candidate, Scenario, Storyboard, AnalysisResult, VisionInsights
from .settings import settings

logger = logging.getLogger(__name__)
app = FastAPI()


class SearchPayload(BaseModel):
    topic: str
    n: int = Field(default=5, ge=1, le=50)
    region: Optional[str] = None
    published_after: Optional[str] = None
    shorts: Optional[bool] = None


class AnalyzePayload(BaseModel):
    video_id: str


class ScenarioPayload(BaseModel):
    video_id: str
    topic: str


class StoryboardPayload(BaseModel):
    scenario: Scenario
    target: Literal["shorts", "youtube"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search", response_model=list[Candidate])
def search(payload: SearchPayload):
    region = payload.region or settings.REGION_CODE
    published_after = payload.published_after or settings.DEFAULT_PUBLISHED_AFTER
    shorts = payload.shorts if payload.shorts is not None else True
    return youtube_client.search_trending(payload.topic, payload.n, region, published_after, shorts)


@app.post("/analyze", response_model=AnalysisResult)
def analyze(payload: AnalyzePayload):
    try:
        return _run_analysis(payload.video_id)
    except RuntimeError as exc:
        logger.exception("Analysis failed for %s", payload.video_id)
        raise HTTPException(500, str(exc))


@app.post("/scenario", response_model=Scenario)
def scenario(payload: ScenarioPayload):
    try:
        analysis = _run_analysis(payload.video_id)
    except RuntimeError as exc:
        logger.exception("Scenario analysis failed for %s", payload.video_id)
        raise HTTPException(500, str(exc))
    return llm_scenario.make_ru_scenario(analysis.transcript, analysis.shots, analysis.key_objects, payload.topic)


@app.post("/storyboard", response_model=Storyboard)
def storyboard(payload: StoryboardPayload):
    try:
        return llm_storyboard.plan_timeline(payload.scenario, payload.target)
    except RuntimeError as exc:
        logger.exception("Storyboard generation failed")
        raise HTTPException(500, str(exc))


def _run_analysis(video_id: str) -> AnalysisResult:
    with media_probe.pull_transient(video_id) as (audio_path, video_path):
        if not audio_path:
            raise RuntimeError("Audio not extracted")
        transcript = stt.transcribe(audio_path)
        vision_data = VisionInsights(shots=[], key_objects=[])
        if video_path:
            vision_data = vision_shots.detect_shots(video_path)
    return AnalysisResult(transcript=transcript, shots=vision_data.shots, key_objects=vision_data.key_objects)
