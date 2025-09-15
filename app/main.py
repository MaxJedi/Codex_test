from fastapi import FastAPI, HTTPException
from . import youtube_client, media_probe, stt, vision_shots, llm_scenario, llm_storyboard
from .schemas import Candidate, Transcript, Shot, Scenario, Storyboard, AnalysisResult
from .settings import settings

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search", response_model=list[Candidate])
def search(payload: dict):
    try:
        topic = payload["topic"]
        n = int(payload.get("n", 5))
        region = payload.get("region", settings.REGION_CODE)
        published_after = payload.get("published_after", settings.DEFAULT_PUBLISHED_AFTER)
        shorts = bool(payload.get("shorts", True))
    except KeyError as e:
        raise HTTPException(400, f"Missing field {e}")
    return youtube_client.search_trending(topic, n, region, published_after, shorts)


@app.post("/analyze", response_model=AnalysisResult)
def analyze(payload: dict) -> AnalysisResult:
    video_id = payload.get("video_id")
    if not video_id:
        raise HTTPException(400, "video_id required")
    with media_probe.pull_transient(video_id) as (audio_path, video_path):
        if not audio_path:
            raise HTTPException(500, "Audio not extracted")
        transcript = stt.transcribe(audio_path)
        if video_path:
            shots = vision_shots.detect_shots(video_path)
        else:
            shots = []
    return AnalysisResult(transcript=transcript, shots=shots)


@app.post("/scenario", response_model=Scenario)
def scenario(payload: dict):
    video_id = payload.get("video_id")
    topic = payload.get("topic")
    if not video_id or not topic:
        raise HTTPException(400, "video_id and topic required")
    analysis = analyze({"video_id": video_id})
    transcript = analysis.transcript
    shots = analysis.shots
    return llm_scenario.make_ru_scenario(transcript, shots, topic)


@app.post("/storyboard", response_model=Storyboard)
def storyboard(payload: dict):
    scenario_data = payload.get("scenario")
    target = payload.get("target")
    if not scenario_data or not target:
        raise HTTPException(400, "scenario and target required")
    scn = Scenario.model_validate(scenario_data)
    return llm_storyboard.plan_timeline(scn, target)
