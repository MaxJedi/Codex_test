from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
import os
import json
import re
import httpx
import shutil
import tempfile
import subprocess
import urllib.parse

from app.schemas.content import Scenario, Storyboard, GeneratedVideo
from app.services import make_ru_scenario, plan_timeline, RunwayVideoService
from app.core.settings import settings
from app.services.storage_service import ensure_dir, save_json
from app.services.media_assembly_service import extract_last_frame, concatenate_videos_in_dir, overlay_title_text
from app.routers.media import analyze
from app.schemas import Transcript, Shot, KeyObject, TextOverlayConfig
from app.schemas.topics import TopicsGenerateRequest, TopicsGenerateResponse, TopicsOverlayRequest, TopicsOverlayResponse, TopicsOverlayItem
from app.schemas.topics import TopicIdea, TopicsOverlayParams
from app.services.storage_service import read_json
from app.services.query_service import generate_search_query
from app.services.query_service import generate_reels_ideas, generate_reel_visual_prompt
from app.services.youtube_service import search_trending
from app.services.stt_service import transcribe
from app.services.vision_service import detect_shots
from app.integrations import cobalt
from app.services.text_overlay_service import TextOverlayService
from app.services.topics_service import generate_topics
import datetime
import logging
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/content", tags=["content"])


def _safe_realpath(path: str) -> str:
    root = os.path.realpath(settings.FILE_BROWSER_ROOT)
    real = os.path.realpath(path)
    if not real.startswith(root.rstrip(os.sep) + os.sep) and real != root:
        raise HTTPException(403, f"path is outside FILE_BROWSER_ROOT: {settings.FILE_BROWSER_ROOT}")
    return real


@router.get("/fs_download")
def fs_download(path: str):
    """Download any file under FILE_BROWSER_ROOT."""
    real = _safe_realpath(path)
    if not os.path.isfile(real):
        raise HTTPException(404, "File not found")
    return FileResponse(real, filename=os.path.basename(real))


@router.get("/fs_ls")
def fs_ls(path: str) -> dict:
    """List directories and mp4 files for arbitrary filesystem browsing (restricted by FILE_BROWSER_ROOT)."""
    real = _safe_realpath(path)
    if not os.path.isdir(real):
        raise HTTPException(404, f"Not a directory: {real}")
    dirs: list[str] = []
    mp4s: list[str] = []
    for name in sorted(os.listdir(real)):
        full = os.path.join(real, name)
        if os.path.isdir(full):
            dirs.append(name)
        elif name.lower().endswith(".mp4"):
            mp4s.append(name)
    parent = os.path.dirname(real)
    parent_allowed = None
    try:
        parent_allowed = _safe_realpath(parent)
    except HTTPException:
        parent_allowed = None
    return {
        "path": real,
        "parent": parent_allowed,
        "dirs": dirs,
        "files": mp4s,
    }


@router.post("/topics_generate", response_model=TopicsGenerateResponse)
def topics_generate(req: TopicsGenerateRequest) -> TopicsGenerateResponse:
    topics = generate_topics(req.n, hint=req.hint)
    return TopicsGenerateResponse(topics=topics)


@router.post("/topics_overlay_batch", response_model=TopicsOverlayResponse)
def topics_overlay_batch(req: TopicsOverlayRequest) -> TopicsOverlayResponse:
    src = _safe_realpath(req.path)
    if not os.path.isfile(src):
        raise HTTPException(404, f"Not a file: {src}")

    out_dir = os.path.join(os.path.dirname(src), "overlay_topics")
    ensure_dir(out_dir)

    p = req.params
    align = p.align if p.align in ("left", "center", "right") else "center"

    results: list[TopicsOverlayItem] = []
    svc = TextOverlayService()

    for idx, topic in enumerate(req.topics, start=1):
        safe = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]+", "_", topic.title).strip("_")
        safe = safe[:60] if safe else f"topic_{idx:02d}"
        output_path = os.path.join(out_dir, f"{idx:02d}_{safe}.mp4")

        title_cfg = TextOverlayConfig(
            text=topic.title,
            font_path=p.font_path,
            font_size=p.min_font_size,
            max_words_per_line=p.words_max,
            align=align,
            center_x=p.center_x,
            center_y=p.title_y,
            font_color=p.font_color,
            outline_color=p.outline_color,
            outline_width=p.outline_width,
            line_spacing=p.line_spacing,
            auto_fit=True,
            padding_pct=p.padding_pct,
            auto_fit_base_font_size=p.base_font_size,
            auto_fit_min_font_size=p.min_font_size,
            auto_fit_min_words_per_line=p.words_min,
            auto_fit_max_words_per_line=p.words_max,
            min_text_coverage_pct=p.coverage_min_pct,
            max_text_coverage_pct=p.coverage_max_pct,
        )

        desc_base = max(p.min_font_size, int(p.base_font_size * 0.75))
        desc_cfg = TextOverlayConfig(
            text=topic.description,
            font_path=p.font_path,
            font_size=p.min_font_size,
            max_words_per_line=p.words_max,
            align=align,
            center_x=p.center_x,
            center_y=min(1.0, p.title_y + 0.06),
            font_color=p.font_color,
            outline_color=p.outline_color,
            outline_width=p.outline_width,
            line_spacing=p.line_spacing,
            auto_fit=True,
            padding_pct=p.padding_pct,
            auto_fit_base_font_size=desc_base,
            auto_fit_min_font_size=p.min_font_size,
            auto_fit_min_words_per_line=p.words_min,
            auto_fit_max_words_per_line=p.words_max,
            min_text_coverage_pct=p.coverage_min_pct,
            max_text_coverage_pct=p.coverage_max_pct,
        )

        try:
            final_path = svc.apply_topic_title_and_description(
                src,
                title_cfg=title_cfg,
                description_cfg=desc_cfg,
                output_path=output_path,
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, f"ffmpeg failed for topic '{topic.title}': {e}")

        results.append(
            TopicsOverlayItem(
                title=topic.title,
                description=topic.description,
                output_path=final_path,
                download_url="/content/fs_download?path=" + urllib.parse.quote(final_path),
            )
        )

    return TopicsOverlayResponse(source_path=src, results=results)


@router.post("/topics_overlay_batch_upload", response_model=TopicsOverlayResponse)
async def topics_overlay_batch_upload(
    video: UploadFile = File(..., description="Source video file"),
    topics_json: str = Form(..., description="JSON array of topics [{title, description}, ...]"),
    params_json: str = Form(..., description="JSON object with overlay params"),
) -> TopicsOverlayResponse:
    import uuid

    try:
        raw_topics = json.loads(topics_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid topics_json: {e}")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise HTTPException(400, "topics_json must be a non-empty JSON array")

    topics: list[TopicIdea] = []
    for item in raw_topics:
        try:
            topics.append(TopicIdea.model_validate(item))
        except Exception as e:
            raise HTTPException(400, f"Invalid topic item: {e}")

    try:
        params = TopicsOverlayParams.model_validate(json.loads(params_json))
    except Exception as e:
        raise HTTPException(400, f"Invalid params_json: {e}")

    overlay_id = f"topics_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "topics_overlays", overlay_id)
    ensure_dir(out_dir)

    input_path = os.path.join(out_dir, "input.mp4")
    with open(input_path, "wb") as f:
        f.write(await video.read())

    # Reuse same logic as /topics_overlay_batch using the saved file path
    req_obj = TopicsOverlayRequest(path=input_path, topics=topics, params=params)
    return topics_overlay_batch(req_obj)


@router.get("/video_info")
def video_info(path: str) -> dict:
    """Return basic video info (resolution, duration) using ffprobe. Path restricted by FILE_BROWSER_ROOT."""
    def _parse_rate(rate: str | None) -> float | None:
        if not rate:
            return None
        s = str(rate).strip()
        if not s or s == "0/0":
            return None
        if "/" in s:
            num_s, den_s = s.split("/", 1)
            try:
                num = float(num_s)
                den = float(den_s)
            except ValueError:
                return None
            if den == 0:
                return None
            return num / den
        try:
            return float(s)
        except ValueError:
            return None

    real = _safe_realpath(path)
    if not os.path.isfile(real):
        raise HTTPException(404, f"Not a file: {real}")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,codec_name,pix_fmt:format=duration,size,bit_rate,format_name",
        "-of",
        "json",
        real,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        data = json.loads(out.decode("utf-8"))
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        avg_frame_rate = stream.get("avg_frame_rate")
        r_frame_rate = stream.get("r_frame_rate")
        fps = _parse_rate(avg_frame_rate) or _parse_rate(r_frame_rate)
        return {
            "path": real,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration_sec": float(fmt.get("duration")) if fmt.get("duration") else None,
            "avg_frame_rate": avg_frame_rate,
            "r_frame_rate": r_frame_rate,
            "fps": fps,
            "codec": stream.get("codec_name"),
            "pix_fmt": stream.get("pix_fmt"),
            "format_name": fmt.get("format_name"),
            "size_bytes": int(fmt.get("size")) if fmt.get("size") else None,
            "bit_rate": int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None,
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"ffprobe failed: {e.output.decode('utf-8', errors='ignore')[:500]}")


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
    prompt = payload.get("prompt")
    duration = int(payload.get("duration", 5))
    ratio = payload.get("ratio") or settings.VIDEO_DEFAULT_RATIO

    if not prompt and not scenario_data:
        raise HTTPException(400, "prompt or scenario required")

    if not prompt and scenario_data:
        scn = Scenario.model_validate(scenario_data)
        if getattr(scn, "scenes", None):
            # Use first scene's visual description as a base prompt
            prompt = scn.scenes[0].visual_description
        else:
            import json as _json
            prompt = _json.dumps(scn.model_dump(), ensure_ascii=False)

    svc = RunwayVideoService()
    result = svc.generate_from_text(prompt_text=prompt, duration=duration, ratio=ratio)
    return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)


@router.post("/video_veo3_vertical", response_model=GeneratedVideo)
def generate_video_veo3_vertical(payload: dict) -> GeneratedVideo:
    """Generate video from prompt using veo3 model in vertical format (9:16).
    
    Expected payload:
    - prompt: text prompt for video generation (required)
    - duration: video duration in seconds (default: 5)
    """
    
    prompt = """A real household kitten, not stylized, sitting on a slightly worn wooden table. Natural posture, subtle uneven fur, tiny random hairs sticking out, small shadow variations on the muzzle. The kitten quietly looks straight ahead at a person off-frame. Eyes reflect the room naturally, with imperfect reflections and tiny light falloff. Shot on Sony FX30, real optical behavior: mild chromatic aberration on high-contrast edges, gentle lens breathing, organic sensor noise in darker areas, soft daylight from a nearby window creating natural gradients on fur. Realistic color temperature, slightly imperfect white balance, micro-dust on the table surface, natural shadows falling in different directions. Camera is fixed, no artificial sharpness, no plastic skin, no symmetry polishing, no AI-cleanup. Depth of field behaves physically: background slightly blurred with real optical bokeh shape, not smoothened. No glossiness, no CGI feel, no smoothing, no HDR look. Only natural documentary realism."""
    if not prompt:
        raise HTTPException(400, "prompt required")
    
    duration = int(payload.get("duration", 5))
    vertical_ratio = "1080:1920"  # 9:16 vertical format
    
    svc = RunwayVideoService()
    result = svc.generate_from_text(
        prompt_text=prompt,
        model="veo3",
        ratio=vertical_ratio,
        duration=duration,
    )
    return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)


@router.post("/video_image_prompt_vertical", response_model=GeneratedVideo)
async def generate_video_image_prompt_vertical(
    image: UploadFile = File(..., description="Image file to use for video generation"),
    prompt: str = Form(..., description="Text prompt for video generation"),
    duration: int = Form(default=5, description="Video duration in seconds"),
) -> GeneratedVideo:
    """Generate video from uploaded image and prompt using gen4_turbo model in vertical format (9:16).
    
    Accepts multipart/form-data with:
    - image: image file (required)
    - prompt: text prompt (required)
    - duration: video duration in seconds (default: 5)
    """
    if not prompt:
        raise HTTPException(400, "prompt required")
    
    # Determine MIME type from uploaded file
    mime_type = image.content_type or "image/png"
    if mime_type not in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        mime_type = "image/png"  # fallback
    
    # Save uploaded file to temporary location
    temp_dir = tempfile.mkdtemp()
    temp_image_path = None
    try:
        # Determine file extension from content type
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
        }
        ext = ext_map.get(mime_type, ".png")
        temp_image_path = os.path.join(temp_dir, f"uploaded_image{ext}")
        
        # Save uploaded file
        with open(temp_image_path, "wb") as f:
            content = await image.read()
            f.write(content)
        
        vertical_ratio = "1080:1920"  # 9:16 vertical format
        
        svc = RunwayVideoService()
        result = svc.generate_from_image_and_text(
            image_path=temp_image_path,
            prompt_text=prompt,
            model="veo3.1",
            ratio=vertical_ratio,
            duration=duration,
            mime_type=mime_type,
        )
        return GeneratedVideo(task_id=result.task_id, status=result.status, url=result.output_url)
    finally:
        # Clean up temporary file and directory
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


@router.get("/video_folders", response_model=list[str])
def list_video_folders() -> list[str]:
    """List available folders under DATA_DIR that may contain videos."""
    base = settings.DATA_DIR
    if not os.path.isdir(base):
        return []
    folders: list[str] = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if os.path.isdir(full):
            folders.append(name)
    return folders


@router.get("/video_files", response_model=list[str])
def list_video_files(folder: str) -> list[str]:
    """List mp4 files inside a selected folder (recursively, relative paths)."""
    base = os.path.join(settings.DATA_DIR, folder)
    if not os.path.isdir(base):
        raise HTTPException(404, f"Folder not found: {folder}")
    result: list[str] = []
    for root, _, files in os.walk(base):
        for fn in files:
            if fn.lower().endswith(".mp4"):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, base)
                result.append(rel)
    result.sort()
    return result


@router.post("/overlay_text")
def overlay_text_on_video(payload: dict) -> dict:
    """Apply text overlay on an existing video inside a chosen folder.

    Expected JSON:
    - folder: name of folder under DATA_DIR (required), e.g. work_id or video_id
    - video_path: relative path inside folder to source video (optional).
        If omitted, tries common defaults or first *.mp4 in folder.
    - config: TextOverlayConfig-compatible object with text and styling.
    """
    folder = payload.get("folder")
    video_path = payload.get("video_path")
    input_path = payload.get("path")
    cfg_data = payload.get("config") or {}
    if not folder and not input_path:
        raise HTTPException(400, "folder or path required")

    if input_path:
        source_full = _safe_realpath(input_path)
        if not os.path.isfile(source_full):
            raise HTTPException(404, f"Source video not found: {source_full}")
        base = os.path.dirname(source_full)
        folder = folder or os.path.basename(base)
    else:
        base = os.path.join(settings.DATA_DIR, folder)
        if not os.path.isdir(base):
            raise HTTPException(404, f"Folder not found: {folder}")

    # Resolve source video path
    source_full: str | None = None if not input_path else source_full
    candidates: list[str] = []
    if video_path:
        candidates.append(os.path.join(base, video_path))
    else:
        # Try some common locations (result_video, video_shots, root)
        defaults = [
            os.path.join(base, "result_video", "full.mp4"),
            os.path.join(base, "result_video", "result.mp4"),
            os.path.join(base, "video_shots", "full.mp4"),
        ]
        candidates.extend(defaults)
        # Fallback: first mp4 in folder
        for root, _, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith(".mp4"):
                    candidates.append(os.path.join(root, fn))
            if candidates:
                break

    for c in candidates:
        if c and os.path.exists(c):
            source_full = c
            break

    if not source_full:
        raise HTTPException(404, "Source video not found; specify video_path or ensure mp4 exists in folder")

    try:
        cfg = TextOverlayConfig.model_validate(cfg_data)
    except Exception as e:
        raise HTTPException(400, f"Invalid config: {e}")

    # Output into subfolder 'overlay'
    overlay_dir = os.path.join(base, "overlay")
    ensure_dir(overlay_dir)
    src_name = os.path.basename(source_full)
    name, ext = os.path.splitext(src_name)
    output_path = os.path.join(overlay_dir, f"{name}_text{ext or '.mp4'}")

    svc = TextOverlayService()
    final_path = svc.apply_text_on_video(source_full, cfg, output_path=output_path)

    rel_output = os.path.relpath(final_path, base)
    return {
        "folder": folder,
        "source": os.path.relpath(source_full, base),
        "output": rel_output,
        "download_url": f"/content/overlay_download?folder={folder}&file={rel_output}",
    }


@router.post("/overlay_text_upload")
async def overlay_text_upload(
    video: UploadFile = File(..., description="Source video file (mp4)"),
    text: str = Form(...),
    font_size: int = Form(48),
    max_words_per_line: int = Form(7),
    align: str = Form("center"),
    center_x: float = Form(0.5),
    center_y: float = Form(0.8),
    font_color: str = Form("#ffffff"),
    outline_color: str = Form("#000000"),
    outline_width: int = Form(2),
    line_spacing: int = Form(4),
    auto_fit: bool = Form(False),
    padding_pct: float = Form(5.0),
    auto_fit_base_font_size: int = Form(120),
    max_text_coverage_pct: float = Form(18.0),
    min_text_coverage_pct: float = Form(8.0),
    auto_fit_min_words_per_line: int = Form(3),
    auto_fit_max_words_per_line: int = Form(14),
    auto_fit_min_font_size: int = Form(14),
    font_path: str = Form(""),
) -> dict:
    """Upload a video (browser file picker) and apply text overlay; returns download URL."""
    import uuid

    if not text.strip():
        raise HTTPException(400, "text required")

    overlay_id = f"overlay_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "overlays", overlay_id)
    ensure_dir(out_dir)

    input_path = os.path.join(out_dir, "input.mp4")
    output_path = os.path.join(out_dir, "output.mp4")

    # Save uploaded video
    with open(input_path, "wb") as f:
        f.write(await video.read())

    cfg = TextOverlayConfig(
        text=text,
        font_path=(font_path or None),
        font_size=font_size,
        max_words_per_line=max_words_per_line,
        align=align if align in ("left", "center", "right") else "center",
        center_x=center_x,
        center_y=center_y,
        font_color=font_color,
        outline_color=outline_color,
        outline_width=outline_width,
        line_spacing=line_spacing,
        auto_fit=auto_fit,
        padding_pct=padding_pct,
        auto_fit_base_font_size=auto_fit_base_font_size,
        max_text_coverage_pct=max_text_coverage_pct,
        min_text_coverage_pct=min_text_coverage_pct,
        auto_fit_min_words_per_line=auto_fit_min_words_per_line,
        auto_fit_max_words_per_line=auto_fit_max_words_per_line,
        auto_fit_min_font_size=auto_fit_min_font_size,
    )

    svc = TextOverlayService()
    svc.apply_text_on_video(input_path, cfg, output_path=output_path)

    # Reuse existing download endpoint by folder+file convention:
    folder = os.path.join("overlays", overlay_id)
    rel_file = "output.mp4"
    return {
        "folder": folder,
        "output": rel_file,
        "download_url": f"/content/overlay_download?folder={folder}&file={rel_file}",
    }


@router.get("/overlay_download")
def overlay_download(folder: str, file: str):
    """Download resulting overlaid video from selected folder."""
    from fastapi.responses import FileResponse

    base = os.path.join(settings.DATA_DIR, folder)
    full = os.path.join(base, file)
    if not os.path.isfile(full):
        raise HTTPException(404, "File not found")

    filename = os.path.basename(full)
    return FileResponse(full, media_type="video/mp4", filename=filename)


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
    ratio = payload.get("ratio") or settings.VIDEO_DEFAULT_RATIO
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
    resume = bool(payload.get("resume", False))

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

    # Determine resume start index based on existing shots
    first_idx = scene_items[0][0]
    existing_indices = set()
    if resume and os.path.isdir(shots_dir):
        for name in os.listdir(shots_dir):
            m = _re.match(r"series_shot_(\d+)\.mp4$", name)
            if not m:
                m = _re.match(r"shot_(\d+)\.mp4$", name)
            if m:
                try:
                    existing_indices.add(int(m.group(1)))
                except ValueError as e:
                    logger.error(f"Error parsing existing index: {e}")

    # Compute start_from as the next missing index after a continuous prefix
    start_from = first_idx
    if resume and existing_indices:
        i = first_idx
        while i in existing_indices:
            i += 1
        start_from = i

    # Prepare first image (skip generating if resuming and it exists)
    first_image_path = os.path.join(images_dir, f"scene_{first_idx:05d}.jpg")
    previous_image_path = None
    need_generate_first_image = True
    if resume and os.path.exists(first_image_path):
        need_generate_first_image = False
        previous_image_path = first_image_path

    if need_generate_first_image:
        # Generate first image from the first scene
        first_scene = scene_items[0][1]
        if isinstance(first_scene, str):
            first_prompt = first_scene
        elif isinstance(first_scene, dict):
            first_prompt = str(first_scene.get("prompt") or first_scene.get("text") or first_scene.get("description") or first_scene)
        else:
            first_prompt = str(first_scene)
        try:
            img_task = svc.generate_image(first_prompt, model=model_t2i, ratio=settings.VIDEO_DEFAULT_RATIO)
            img_url = img_task.output_url
        except Exception as e:
            raise HTTPException(500, f"Image generation failed: {e}")
        if not img_url:
            raise HTTPException(500, "Image generation returned no URL")

        try:
            with httpx.stream("GET", img_url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(first_image_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            raise HTTPException(500, f"Failed to download generated image: {e}")
        previous_image_path = first_image_path

    # If resuming from a later index, set previous_image_path from last completed video frame
    if start_from > first_idx:
        prev_idx = start_from - 1
        prev_last_frame = os.path.join(images_dir, f"scene_{prev_idx:05d}_last.jpg")
        if not os.path.exists(prev_last_frame):
            prev_video = os.path.join(shots_dir, f"series_shot_{prev_idx:05d}.mp4")
            if not os.path.exists(prev_video):
                raise HTTPException(400, f"Resume requested, but previous video not found: {prev_video}")
            try:
                extract_last_frame(prev_video, prev_last_frame)
            except Exception as e:
                raise HTTPException(500, f"Failed to extract last frame from previous video: {e}")
        previous_image_path = prev_last_frame

    # 3..5) Chain videos
    for idx, scene in scene_items:
        if idx < start_from:
            continue
        if isinstance(scene, str):
            prompt = scene
        elif isinstance(scene, dict):
            prompt = str(scene.get("prompt") or scene.get("text") or scene.get("description") or scene)
        else:
            prompt = str(scene)
        video_path = os.path.join(shots_dir, f"series_shot_{idx:05d}.mp4")
        if resume and os.path.exists(video_path):
            # Skip regeneration, but ensure we have the last frame for chaining
            next_image_path = os.path.join(images_dir, f"scene_{idx:05d}_last.jpg")
            if not os.path.exists(next_image_path):
                try:
                    extract_last_frame(video_path, next_image_path)
                except Exception as e:
                    results.append({"scene": idx, "status": "frame_extract_error", "error": str(e)})
                    break
            previous_image_path = next_image_path
            results.append({"scene": idx, "status": "skipped_existing", "path": video_path})
            continue
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

    # Concatenate all generated videos into a single file
    full_video_dir = os.path.join(settings.DATA_DIR, f"video_{video_id}") if video_id else os.path.join(settings.DATA_DIR, "video")
    ensure_dir(full_video_dir)
    full_video_tmp = None
    full_video_path = None
    try:
        full_video_tmp = concatenate_videos_in_dir(shots_dir, pattern="series_shot_*.mp4", output_name="full.mp4")
        # Move to requested directory
        full_video_path = os.path.join(full_video_dir, os.path.basename(full_video_tmp))
        try:
            os.replace(full_video_tmp, full_video_path)
        except Exception:
            shutil.copy2(full_video_tmp, full_video_path)
    except Exception as e:
        # Append concat error but still return partial results
        results.append({"scene": None, "status": "concat_error", "error": str(e)})

    return {"video_id": video_id, "images_dir": images_dir, "shots_dir": shots_dir, "full_video_dir": full_video_dir, "full_video_path": full_video_path, "resumed": resume, "start_from": start_from, "results": results}



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


@router.post("/generate_from_prompt")
def generate_from_prompt(payload: dict) -> dict:
    """Full pipeline from user text to final video with resume support.

    Request fields:
    - text: user free-form request (required unless resuming)
    - n: number of top search videos to analyze (default 3)
    - folder or video_id: resume/use specific working folder under DATA_DIR (e.g., data_25_10_2025_13_45)
    - resume: bool flag to resume from existing state (default False)
    - region, published_after: optional YouTube search overrides (fallback to settings)

    Creates DATA_DIR/<work_id>/ with subfolders:
    frames, images, scenario, input_video, video_shots, result_video, transcript, vision
    """
    user_text = payload.get("text")
    n = int(payload.get("n", settings.DEFAULT_SEARCH_VIDEOS_COUNT))
    resume = bool(payload.get("resume", False))
    work_id = payload.get("folder") or payload.get("video_id")
    region = payload.get("region") or settings.REGION_CODE
    published_after = payload.get("published_after") or settings.DEFAULT_PUBLISHED_AFTER

    # Determine working directory
    if not work_id:
        ts = datetime.datetime.now().strftime("%d_%m_%Y_%H_%M")
        work_id = f"data_{ts}"
    base_dir = os.path.join(settings.DATA_DIR, work_id)

    frames_dir = os.path.join(base_dir, "frames")
    images_dir = os.path.join(base_dir, "images")
    scenario_dir = os.path.join(base_dir, "scenario")
    input_video_dir = os.path.join(base_dir, "input_video")
    video_shots_dir = os.path.join(base_dir, "video_shots")
    result_video_dir = os.path.join(base_dir, "result_video")
    transcript_dir = os.path.join(base_dir, "transcript")
    vision_dir = os.path.join(base_dir, "vision")

    for d in [base_dir, frames_dir, images_dir, scenario_dir, input_video_dir, video_shots_dir, result_video_dir, transcript_dir, vision_dir]:
        ensure_dir(d)

    # 1) Build search query (unless resuming with existing state)
    query = None
    if resume:
        # Try to reuse stored query
        query_json = os.path.join(base_dir, "search_query.json")
        if os.path.exists(query_json):
            try:
                qd = read_json(query_json)
                query = qd.get("query")
            except Exception as e:
                logger.error(f"Error reading search query: {e}")
                pass
    if not query:
        if not user_text:
            raise HTTPException(400, "text required when not resuming")
        query = generate_search_query(user_text)
        save_json(os.path.join(base_dir, "search_query.json"), {"text": user_text, "query": query})

    # 2) Search videos
    candidates = search_trending(query, n=n, region=region, published_after=published_after, shorts=True)
    save_json(os.path.join(base_dir, "candidates.json"), [c.model_dump(mode="json") for c in candidates])
    video_ids = [c.video_id for c in candidates][:n]
    if not video_ids:
        return {
            "work_id": work_id,
            "base_dir": base_dir,
            "query": query,
            "message": "no candidates found for the query",
            "series": None,
        }

    # 3) Analyze first N videos (transcript + vision)
    for idx, vid in enumerate(video_ids, start=1):
        vid_mp4 = os.path.join(input_video_dir, f"video_{idx:05d}.mp4")
        aud_mp3 = os.path.join(input_video_dir, f"audio_{idx:05d}.mp3")
        tr_out = os.path.join(transcript_dir, f"transcript_{idx:05d}.json")
        vs_out = os.path.join(vision_dir, f"vision_{idx:05d}.json")

        need_download = not os.path.exists(vid_mp4) or os.path.getsize(vid_mp4) < 1024
        need_transcript = not os.path.exists(tr_out)
        need_vision = not os.path.exists(vs_out)

        if need_download or need_transcript or need_vision:
            audio_path, video_path = cobalt.pull_transient(vid)
            # Copy into workspace
            try:
                if need_download and video_path and os.path.exists(video_path):
                    with open(video_path, "rb") as _src, open(vid_mp4, "wb") as _dst:
                        _dst.write(_src.read())
                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, "rb") as _src, open(aud_mp3, "wb") as _dst:
                        _dst.write(_src.read())
            except Exception as e:
                logger.error(f"Error copying video or audio: {e}")
                pass

        if need_transcript and os.path.exists(aud_mp3):
            tr = transcribe(aud_mp3)
            save_json(tr_out, tr.model_dump())

        if need_vision and os.path.exists(vid_mp4):
            shots, key_objects = detect_shots(vid_mp4, work_id)
            save_json(vs_out, {
                "shots": [s.model_dump() for s in shots],
                "key_objects": [ko.model_dump() for ko in key_objects],
            })

    # 4) Build aggregated data and generate scenario (if not exists)
    scenario_path = os.path.join(scenario_dir, "scenario_data.json")
    if not os.path.exists(scenario_path):
        # Aggregate transcripts
        segments: list[dict] = []
        for p in sorted(os.listdir(transcript_dir)):
            if p.endswith('.json'):
                try:
                    data = read_json(os.path.join(transcript_dir, p))
                    for seg in data.get("segments", data if isinstance(data, list) else []):
                        segments.append({
                            "text": str(seg.get("text", "")),
                            "start": float(seg.get("start", 0)),
                            "end": float(seg.get("end", 0)),
                        })
                except Exception as e:
                    logger.error(f"Error reading transcript: {e}")
                    continue

        # Aggregate vision
        agg_shots: list[dict] = []
        agg_objs: list[dict] = []
        for p in sorted(os.listdir(vision_dir)):
            if p.endswith('.json'):
                try:
                    v = read_json(os.path.join(vision_dir, p))
                    for s in v.get("shots", []):
                        agg_shots.append(s)
                    for o in v.get("key_objects", []):
                        agg_objs.append(o)
                except Exception as e:
                    logger.error(f"Error reading vision: {e}")
                    continue

        # Convert to models
        transcript = Transcript.model_validate({"segments": segments})
        shots = [Shot(start_sec=float(s.get("start_sec", s.get("start", 0.0))), end_sec=float(s.get("end_sec", s.get("end", 0.0)))) for s in agg_shots]
        key_objects = [
            KeyObject(
                description=str(o.get("description", "")),
                start_sec=float(o.get("start_sec", o.get("start", 0.0))),
                end_sec=float(o.get("end_sec", o.get("end", 0.0))),
                confidence=(float(o["confidence"]) if o.get("confidence") is not None else None),
                categories=list(o.get("categories", []) or []),
            ) for o in agg_objs
        ]

        scn = make_ru_scenario(transcript, shots, query, key_objects)
        save_json(scenario_path, scn)

    # 5) Generate series videos and concat (reusing existing endpoint logic with resume)
    series_res = generate_series({
        "video_id": work_id,
        "scenario_path": scenario_path,
        "resume": True,
    })

    return {
        "work_id": work_id,
        "base_dir": base_dir,
        "query": query,
        "series": series_res,
    }


@router.post("/reels")
def generate_reels(payload: dict) -> dict:
    """Generate Instagram reels set from ideas or by prompting GPT for ideas.

    Input (optional):
    - ideas: list of strings (titles) or dict {title: description}
    - n: number of ideas if ideas not provided (default from settings)
    - topic: optional hint for GPT for idea generation
    - duration: seconds per reel (default 8)
    - ratio: aspect ratio (default settings.VIDEO_DEFAULT_RATIO)
    - overlay_title: whether to burn title at top (default True)
    Generation steps per idea:
    1) Generate a still image (first frame concept) from the scenario prompt and save to images/
    2) Generate the final video from that image + the same prompt (gen4_turbo)
    """
    duration = int(payload.get("duration", 8))
    ratio = payload.get("ratio") or settings.VIDEO_DEFAULT_RATIO
    overlay_title = bool(payload.get("overlay_title", True))
    n = int(payload.get("n", settings.REELS_DEFAULT_COUNT))
    topic = payload.get("topic")
    ideas = payload.get("ideas")

    ts = datetime.datetime.now().strftime("%d_%m_%y_%H_%M_%S")
    work_id = f"reels_{ts}"
    base_dir = os.path.join(settings.DATA_DIR, work_id)
    videos_dir = os.path.join(base_dir, "videos")
    scenarios_dir = os.path.join(base_dir, "scenarios")
    images_dir = os.path.join(base_dir, "images")
    ensure_dir(base_dir)
    ensure_dir(videos_dir)
    ensure_dir(scenarios_dir)
    ensure_dir(images_dir)

    # Prepare titles -> descriptions
    titles_map: dict[str, str] = {}
    if isinstance(ideas, dict):
        titles_map = {str(k): str(v) for k, v in ideas.items()}
    elif isinstance(ideas, list):
        for t in ideas[:n]:
            titles_map[str(t)] = ""
    else:
        titles_map = generate_reels_ideas(n, topic_hint=topic) or {}
        if not titles_map:
            raise HTTPException(500, "Failed to generate reels ideas")

    save_json(os.path.join(base_dir, "ideas.json"), titles_map)

    svc = RunwayVideoService()
    results = []
    for idx, (title, desc) in enumerate(list(titles_map.items()), start=1):
        # Ask GPT to generate the concise visual prompt (scene/atmosphere)
        scenario_text = generate_reel_visual_prompt(title, desc)
        print(f"Scenario text: {scenario_text}")
        save_json(os.path.join(scenarios_dir, f"scenario_{idx:05d}.json"), {"title": title, "description": desc, "scenario": scenario_text})

        # 1) Generate still image (first frame concept)
        image_url = None
        image_path = os.path.join(images_dir, f"image_{idx:05d}.jpg")
        try:
            img_task = svc.generate_image(scenario_text, ratio=ratio)
            image_url = img_task.output_url
        except Exception as e:
            results.append({"index": idx, "title": title, "status": "image_error", "error": str(e)})
            continue
        if not image_url:
            results.append({"index": idx, "title": title, "status": "no_image_output"})
            continue
        try:
            with httpx.stream("GET", image_url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(image_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            results.append({"index": idx, "title": title, "status": "image_download_error", "error": str(e), "url": image_url})
            continue

        # 2) Generate video from the image + scenario
        try:
            print(f"Generating video from scenario text: {scenario_text}")
            task = svc.generate_from_image_and_text(
                image_path=image_path,
                prompt_text=scenario_text,
                model="gen4_turbo",
                ratio=ratio,
                duration=duration,
                mime_type="image/jpeg",
            )
            url = task.output_url
        except Exception as e:
            results.append({"index": idx, "title": title, "status": "error", "error": str(e)})
            continue
        if not url:
            results.append({"index": idx, "title": title, "status": "no_output"})
            continue

        raw_path = os.path.join(videos_dir, f"reel_{idx:05d}.mp4")
        try:
            with httpx.stream("GET", url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(raw_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            results.append({"index": idx, "title": title, "status": "download_error", "error": str(e), "url": url})
            continue

        final_path = raw_path
        if overlay_title:
            out_path = os.path.join(videos_dir, f"reel_{idx:05d}_title.mp4")
            try:
                overlay_title_text(raw_path, title, out_path, font_path=settings.DRAW_TEXT_FONT_PATH)
                final_path = out_path
            except Exception as e:
                # If overlay fails, keep raw video
                results.append({"index": idx, "title": title, "status": "overlay_error", "error": str(e), "path": raw_path})
                final_path = raw_path

        results.append({"index": idx, "title": title, "description": desc, "status": "ok", "url": url, "path": final_path})

    return {
        "work_id": work_id,
        "base_dir": base_dir,
        "videos_dir": videos_dir,
        "scenarios_dir": scenarios_dir,
        "images_dir": images_dir,
        "count": len(results),
        "results": results,
    }


@router.post("/image_to_video")
def image_to_video(
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    ratio: str | None = Form(default="2160:3840"),  # vertical 4K
    duration: int = Form(default=8),
    model: str | None = Form(default="veo3"),
) -> dict:
    """Generate a vertical 4K video from an uploaded image and optional prompt (default model: veo3)."""
    # Persist upload to temp file
    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        tmp.write(image.file.read())
    mime = image.content_type or "image/jpeg"

    svc = RunwayVideoService()
    try:
        task = svc.generate_from_image_and_text(
            image_path=tmp_path,
            prompt_text=prompt or "",
            model=model or "veo3",
            ratio=ratio or "2160:3840",
            duration=duration,
            mime_type=mime,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    url = task.output_url
    saved_path = None
    if url:
        out_dir = os.path.join(settings.DATA_DIR, "result_video")
        ensure_dir(out_dir)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(out_dir, f"image_to_video_{ts}.mp4")
        try:
            with httpx.stream("GET", url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(saved_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            saved_path = None
            return {"status": task.status, "url": url, "error": str(e)}

    return {"status": task.status, "url": url, "path": saved_path}

@router.post("/image_to_image")
def image_to_image(
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    ratio: str | None = Form(default="1080:1920"),
    model: str | None = Form(default=None),  # default integration: gen4_image
) -> dict:
    """Generate a vertical image from an uploaded image plus prompt (image-to-image)."""
    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        tmp.write(image.file.read())
    mime = image.content_type or "image/jpeg"

    svc = RunwayVideoService()
    try:
        task = svc.generate_image_from_image_and_text(
            image_path=tmp_path,
            prompt_text=prompt or "",
            model=model,
            ratio=ratio or "1248x832",
            mime_type=mime,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    url = task.output_url
    saved_path = None
    if url:
        out_dir = os.path.join(settings.DATA_DIR, settings.IMAGES_DIRNAME)
        ensure_dir(out_dir)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(out_dir, f"image_to_image_{ts}.jpg")
        try:
            with httpx.stream("GET", url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(saved_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            return {"status": task.status, "url": url, "error": str(e)}

    return {"status": task.status, "url": url, "path": saved_path}

@router.post("/text_to_image")
def text_to_image(payload: dict) -> dict:
    """Generate a vertical 4K image from text prompt (default model: gen4_image)."""
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(400, "prompt is required")
    ratio = payload.get("ratio") or "1080:1920"
    model = payload.get("model") or None  # use integration default (gen4_image)

    svc = RunwayVideoService()
    task = svc.generate_image(prompt_text=prompt, ratio=ratio, model=model)
    url = task.output_url

    saved_path = None
    if url:
        out_dir = os.path.join(settings.DATA_DIR, settings.IMAGES_DIRNAME)
        ensure_dir(out_dir)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(out_dir, f"text_to_image_{ts}.jpg")
        try:
            with httpx.stream("GET", url, timeout=settings.OPENAI_TIMEOUT_SECONDS) as resp:
                resp.raise_for_status()
                with open(saved_path, "wb") as outf:
                    for chunk in resp.iter_bytes():
                        outf.write(chunk)
        except Exception as e:
            saved_path = None
            return {"status": task.status, "url": url, "error": str(e)}

    return {"status": task.status, "url": url, "path": saved_path}
