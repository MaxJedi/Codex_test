from fastapi import APIRouter, HTTPException
import os
import json
import re
import httpx

from app.schemas.content import Scenario, Storyboard, GeneratedVideo
from app.services import make_ru_scenario, plan_timeline, RunwayVideoService
from app.core.settings import settings
from app.services.storage_service import ensure_dir
from app.services.media_assembly_service import extract_last_frame
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
    result = svc.generate_from_text(scn, duration=duration, ratio=ratio)
    return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)


@router.post("/generate_full_video")
def generate_full_video(payload: dict) -> dict:
    """Generate per-scene videos using scenario JSON and corresponding frames.

    Expected input:
    - video_id: optional; if provided, frames are taken from data/<video_id>/frames and outputs to data/<video_id>/video_shots
    - scenario_path: optional explicit path to JSON with scenes (defaults to data/scenario/scenario_data.json, then .../scenario_messages.json)
    - ratio: optional video ratio (default 1280:720)
    - duration: optional per-scene duration seconds (default 6)
    - model: optional Runway model override
    """
    video_id = payload.get("video_id")
    ratio = payload.get("ratio", "1280:720")
    duration = int(payload.get("duration", 6))
    model = payload.get("model")

    # Resolve frames directory and output directory
    if video_id:
        base_dir = os.path.join(settings.DATA_DIR, video_id)
        frames_dir = os.path.join(base_dir, "frames")
        out_dir = os.path.join(base_dir, "video_shots")
    else:
        frames_dir = os.path.join(settings.DATA_DIR, settings.FRAMES_DIR)
        out_dir = os.path.join(settings.DATA_DIR, "video_shots")
    ensure_dir(out_dir)

    # Resolve scenario JSON path
    scenario_path = payload.get("scenario_path")
    if not scenario_path:
        # Try common locations
        base_scn_dir = os.path.join(settings.DATA_DIR, "scenario")
        candidate_paths = [
            os.path.join(base_scn_dir, "scenario_data.json"),
            os.path.join(base_scn_dir, "scenario_messages.json"),
        ]
        if video_id:
            candidate_paths.insert(0, os.path.join(settings.DATA_DIR, video_id, "scenario_data.json"))
            candidate_paths.insert(1, os.path.join(settings.DATA_DIR, video_id, "scenario_messages.json"))
        scenario_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if not scenario_path or not os.path.exists(scenario_path):
        raise HTTPException(400, "scenario JSON not found; provide scenario_path or generate scenario first")

    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_obj = json.load(f)

    # Extract scenes mapping; handle either {scene_1: {...}} or nested under key
    if isinstance(scenario_obj, dict):
        scenes_dict = scenario_obj
        # Some outputs may wrap under a root key like "scenes"
        if "scenes" in scenario_obj and isinstance(scenario_obj["scenes"], dict):
            scenes_dict = scenario_obj["scenes"]
    else:
        raise HTTPException(400, "Invalid scenario JSON format")

    # Collect scene keys in order scene_1..scene_N
    scene_items = []
    for key, value in scenes_dict.items():
        m = re.match(r"scene_(\d+)$", str(key))
        if m:
            idx = int(m.group(1))
            scene_items.append((idx, value))
    if not scene_items:
        raise HTTPException(400, "No scenes found in scenario JSON (scene_1, scene_2, ...)")
    scene_items.sort(key=lambda x: x[0])

    svc = RunwayVideoService()
    results = []
    for idx, scene in scene_items:
        # Determine prompt text from scene
        if isinstance(scene, str):
            prompt_text = scene
        elif isinstance(scene, dict):
            prompt_text = str(scene.get("prompt") or scene.get("text") or scene.get("description") or scene)
        else:
            prompt_text = str(scene)

        frame_name = f"frame_{idx:05d}.jpg"
        frame_path = os.path.join(frames_dir, frame_name)
        if not os.path.exists(frame_path):
            results.append({
                "scene": idx,
                "status": "frame_missing",
                "frame": frame_path,
            })
            continue

        try:
            task = svc.generate_from_image_and_text(
                image_path=frame_path,
                prompt_text=prompt_text,
                model=model,
                ratio=ratio,
                duration=duration,
                mime_type="image/jpeg",
            )
            output_url = task.output_url
        except Exception as e:
            results.append({
                "scene": idx,
                "status": "error",
                "error": str(e),
            })
            continue

        saved_path = None
        if output_url:
            shot_name = f"shot_{idx:05d}.mp4"
            saved_path = os.path.join(out_dir, shot_name)
            try:
                with httpx.stream("GET", output_url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                    resp.raise_for_status()
                    with open(saved_path, "wb") as outf:
                        for chunk in resp.iter_bytes():
                            outf.write(chunk)
            except Exception as e:
                results.append({
                    "scene": idx,
                    "status": "download_error",
                    "url": output_url,
                    "error": str(e),
                })
                continue

        results.append({
            "scene": idx,
            "status": task.status,
            "url": output_url,
            "path": saved_path,
        })

    return {"video_id": video_id, "output_dir": out_dir, "results": results}

@router.post("/generate_series")
def generate_series(payload: dict) -> dict:
    """Generate a series of videos:
    1) Read scenario JSON from disk
    2) Generate an IMAGE from the first scene (text-to-image)
    3) Generate a VIDEO from that image and the first scene's prompt, save into video_shots
    4) Extract last frame of the video and use it as the image for the next scene
    5) Repeat until last scene
    Paths are configurable via settings (DATA_DIR, VIDEO_SHOTS_DIRNAME, IMAGES_DIRNAME).
    """
    video_id = payload.get("video_id")
    ratio = payload.get("ratio", "1280:720")
    duration = int(payload.get("duration", 6))
    model_t2i = payload.get("model_text_to_image")
    model_i2v = payload.get("model_image_to_video")
    scenario_path = payload.get("scenario_path")

    # Resolve dirs
    if video_id:
        base_dir = os.path.join(settings.DATA_DIR, video_id)
    else:
        base_dir = settings.DATA_DIR
    images_dir = os.path.join(base_dir, settings.IMAGES_DIRNAME)
    shots_dir = os.path.join(base_dir, settings.VIDEO_SHOTS_DIRNAME)
    ensure_dir(images_dir)
    ensure_dir(shots_dir)

    # Resolve scenario JSON path
    if not scenario_path:
        base_scn_dir = os.path.join(settings.DATA_DIR, "scenario")
        candidate_paths = [
            os.path.join(base_scn_dir, "scenario_data.json"),
            os.path.join(base_scn_dir, "scenario_messages.json"),
        ]
        if video_id:
            candidate_paths.insert(0, os.path.join(base_dir, "scenario_data.json"))
            candidate_paths.insert(1, os.path.join(base_dir, "scenario_messages.json"))
        scenario_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if not scenario_path or not os.path.exists(scenario_path):
        raise HTTPException(400, "scenario JSON not found; provide scenario_path or generate scenario first")

    # Load and parse scenes
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_obj = json.load(f)
    if isinstance(scenario_obj, dict):
        scenes_dict = scenario_obj.get("scenes") if isinstance(scenario_obj.get("scenes"), dict) else scenario_obj
    else:
        raise HTTPException(400, "Invalid scenario JSON format")
    import re as _re
    scene_items = []
    for key, value in scenes_dict.items():
        m = _re.match(r"scene_(\d+)$", str(key))
        if m:
            idx = int(m.group(1))
            scene_items.append((idx, value))
    if not scene_items:
        raise HTTPException(400, "No scenes found in scenario JSON (scene_1, scene_2, ...)")
    scene_items.sort(key=lambda x: x[0])

    svc = RunwayVideoService()
    results = []

    # 2) Generate first image
    first_idx, first_scene = scene_items[0]
    if isinstance(first_scene, str):
        first_prompt = first_scene
    elif isinstance(first_scene, dict):
        first_prompt = str(first_scene.get("prompt") or first_scene.get("text") or first_scene.get("description") or first_scene)
    else:
        first_prompt = str(first_scene)
    try:
        img_task = svc.generate_image(first_prompt, model=model_t2i, ratio="1920:1080")
        img_url = img_task.output_url
    except Exception as e:
        raise HTTPException(500, f"Image generation failed: {e}")
    if not img_url:
        raise HTTPException(500, "Image generation returned no URL")

    # Download first image
    first_image_path = os.path.join(images_dir, f"scene_{first_idx:05d}.jpg")
    try:
        with httpx.stream("GET", img_url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
            resp.raise_for_status()
            with open(first_image_path, "wb") as outf:
                for chunk in resp.iter_bytes():
                    outf.write(chunk)
    except Exception as e:
        raise HTTPException(500, f"Failed to download generated image: {e}")

    # 3..5) Chain videos
    previous_image_path = first_image_path
    for idx, scene in scene_items:
        if isinstance(scene, str):
            prompt = scene
        elif isinstance(scene, dict):
            prompt = str(scene.get("prompt") or scene.get("text") or scene.get("description") or scene)
        else:
            prompt = str(scene)
        try:
            video_task = svc.generate_from_image_and_text(
                image_path=previous_image_path,
                prompt_text=prompt,
                model=model_i2v,
                ratio=ratio,
                duration=duration,
                mime_type="image/jpeg",
            )
            video_url = video_task.output_url
        except Exception as e:
            results.append({"scene": idx, "status": "error", "error": str(e)})
            break
        if not video_url:
            results.append({"scene": idx, "status": "no_output"})
            break

        # Save video
        video_path = os.path.join(shots_dir, f"series_shot_{idx:05d}.mp4")
        try:
            with httpx.stream("GET", video_url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(video_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            results.append({"scene": idx, "status": "download_error", "error": str(e), "url": video_url})
            break

        results.append({"scene": idx, "status": video_task.status, "url": video_url, "path": video_path})

        # Extract last frame for next iteration
        next_image_path = os.path.join(images_dir, f"scene_{idx:05d}_last.jpg")
        try:
            extract_last_frame(video_path, next_image_path)
            previous_image_path = next_image_path
        except Exception as e:
            results.append({"scene": idx, "status": "frame_extract_error", "error": str(e)})
            break

    return {"video_id": video_id, "images_dir": images_dir, "shots_dir": shots_dir, "results": results}

