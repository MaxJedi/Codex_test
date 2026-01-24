import json
import os
import subprocess
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.core.settings import settings
from app.schemas import (
    TextOverlayConfig,
    TopicsGenerateRequest,
    TopicsGenerateResponse,
    TopicsOverlayRequest,
    TopicsOverlayResponse,
    TopicsOverlayItem,
    TopicIdea,
    TopicsOverlayParams,
)
from app.services.text_overlay_service import TextOverlayService
from app.services.storage_service import ensure_dir
from app.services.topics_service import generate_topics, generate_long_descriptions


router = APIRouter(prefix="/content", tags=["content"])


def _safe_realpath(path: str) -> str:
    root = os.path.realpath(settings.FILE_BROWSER_ROOT)
    real = os.path.realpath(path)
    if not real.startswith(root.rstrip(os.sep) + os.sep) and real != root:
        raise HTTPException(403, f"path is outside FILE_BROWSER_ROOT: {settings.FILE_BROWSER_ROOT}")
    return real


@router.get("/fs_ls")
def fs_ls(path: str) -> dict:
    real = _safe_realpath(path)
    if not os.path.isdir(real):
        raise HTTPException(404, f"Not a directory: {real}")
    dirs: list[str] = []
    files: list[str] = []
    for name in sorted(os.listdir(real)):
        full = os.path.join(real, name)
        if os.path.isdir(full):
            dirs.append(name)
        elif name.lower().endswith(".mp4"):
            files.append(name)
    return {"path": real, "dirs": dirs, "files": files}


@router.get("/video_info")
def video_info(path: str) -> dict:
    real = _safe_realpath(path)
    if not os.path.isfile(real):
        raise HTTPException(404, f"Not a file: {real}")
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,codec_name,bit_rate",
        "-show_entries", "format=duration,size",
        "-of", "json",
        real,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    data = json.loads(out.decode("utf-8"))
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    fps = None
    try:
        fr = stream.get("avg_frame_rate")
        if fr and isinstance(fr, str) and "/" in fr:
            num, den = fr.split("/")
            fps = float(num) / float(den) if float(den) != 0 else None
    except Exception:
        fps = None
    return {
        "path": real,
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration_sec": float(fmt.get("duration")) if fmt.get("duration") else None,
        "fps": fps,
        "codec": stream.get("codec_name"),
        "bit_rate": int(stream.get("bit_rate")) if stream.get("bit_rate") else None,
        "size_bytes": int(fmt.get("size")) if fmt.get("size") else None,
    }


@router.post("/overlay_text")
def overlay_text_on_video(payload: dict) -> dict:
    input_path = payload.get("path")
    cfg_data = payload.get("config") or {}
    if not input_path:
        raise HTTPException(400, "path required")
    source_full = _safe_realpath(input_path)
    if not os.path.isfile(source_full):
        raise HTTPException(404, f"Source video not found: {source_full}")

    cfg = TextOverlayConfig.model_validate(cfg_data)
    overlay_id = f"overlay_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "overlays", overlay_id)
    ensure_dir(out_dir)
    output_path = os.path.join(out_dir, "output.mp4")

    svc = TextOverlayService()
    svc.apply_text_on_video(source_full, cfg, output_path=output_path)

    folder = os.path.join("overlays", overlay_id)
    rel_file = "output.mp4"
    return {
        "source": source_full,
        "output": rel_file,
        "download_url": f"/content/overlay_download?folder={folder}&file={rel_file}",
    }


@router.post("/overlay_text_upload")
async def overlay_text_upload(
    video: UploadFile = File(...),
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
) -> dict:
    overlay_id = f"overlay_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "overlays", overlay_id)
    ensure_dir(out_dir)
    input_path = os.path.join(out_dir, "input.mp4")
    output_path = os.path.join(out_dir, "output.mp4")

    with open(input_path, "wb") as f:
        f.write(await video.read())

    cfg = TextOverlayConfig(
        text=text,
        font_size=font_size,
        max_words_per_line=max_words_per_line,
        align=align if align in ("left", "center", "right") else "center",
        center_x=center_x,
        center_y=center_y,
        font_color=font_color,
        outline_color=outline_color,
        outline_width=outline_width,
        line_spacing=line_spacing,
        auto_fit=bool(auto_fit),
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

    folder = os.path.join("overlays", overlay_id)
    return {
        "output": "output.mp4",
        "download_url": f"/content/overlay_download?folder={folder}&file=output.mp4",
    }


@router.get("/overlay_download")
def overlay_download(folder: str, file: str):
    base = os.path.join(settings.DATA_DIR, folder)
    full = os.path.join(base, file)
    if not os.path.isfile(full):
        raise HTTPException(404, "File not found")
    return FileResponse(full, media_type="video/mp4", filename=os.path.basename(full))


@router.post("/topics_generate", response_model=TopicsGenerateResponse)
def topics_generate(payload: TopicsGenerateRequest):
    topics = generate_topics(payload.n, payload.hint)
    return TopicsGenerateResponse(topics=topics)


def _build_topic_cfg(text: str, params: TopicsOverlayParams, *, y: float) -> TextOverlayConfig:
    return TextOverlayConfig(
        text=text,
        align=params.align,
        center_x=0.5,
        center_y=y,
        auto_fit=True,
        padding_pct=params.padding_pct,
        auto_fit_base_font_size=params.base_font_size,
        auto_fit_min_font_size=params.min_font_size,
        auto_fit_min_words_per_line=params.words_min,
        auto_fit_max_words_per_line=params.words_max,
        min_text_coverage_pct=params.coverage_min_pct,
        max_text_coverage_pct=params.coverage_max_pct,
    )


@router.post("/topics_overlay_batch", response_model=TopicsOverlayResponse)
def topics_overlay_batch(payload: TopicsOverlayRequest):
    source = _safe_realpath(payload.path)
    if not os.path.isfile(source):
        raise HTTPException(404, f"Source video not found: {source}")

    overlay_id = f"topics_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "topics", overlay_id)
    ensure_dir(out_dir)

    svc = TextOverlayService()
    long_map = generate_long_descriptions(payload.topics)
    results: list[TopicsOverlayItem] = []

    for idx, topic in enumerate(payload.topics, start=1):
        title_cfg = _build_topic_cfg(topic.title, payload.params, y=payload.params.title_y)
        desc_cfg = _build_topic_cfg(topic.description, payload.params, y=payload.params.title_y)
        output_path = os.path.join(out_dir, f"topic_{idx:03d}.mp4")
        svc.apply_topic_title_and_description(
            source,
            title_cfg=title_cfg,
            description_cfg=desc_cfg,
            output_path=output_path,
        )
        rel_file = os.path.basename(output_path)
        results.append(TopicsOverlayItem(
            title=topic.title,
            description=topic.description,
            long_description=long_map.get(topic.title),
            output_path=rel_file,
            download_url=f"/content/overlay_download?folder=topics/{overlay_id}&file={rel_file}",
        ))

    return TopicsOverlayResponse(source_path=source, results=results)


@router.post("/topics_overlay_batch_upload", response_model=TopicsOverlayResponse)
async def topics_overlay_batch_upload(
    video: UploadFile = File(...),
    topics_json: str = Form(...),
    params_json: str = Form(...),
):
    try:
        topics_data = json.loads(topics_json)
        params_data = json.loads(params_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in topics_json or params_json")

    topics = [TopicIdea.model_validate(t) for t in (topics_data or [])]
    params = TopicsOverlayParams.model_validate(params_data or {})
    if not topics:
        raise HTTPException(400, "topics required")

    overlay_id = f"topics_{uuid.uuid4().hex[:12]}"
    out_dir = os.path.join(settings.DATA_DIR, "topics", overlay_id)
    ensure_dir(out_dir)
    input_path = os.path.join(out_dir, "input.mp4")

    with open(input_path, "wb") as f:
        f.write(await video.read())

    svc = TextOverlayService()
    long_map = generate_long_descriptions(topics)
    results: list[TopicsOverlayItem] = []
    for idx, topic in enumerate(topics, start=1):
        title_cfg = _build_topic_cfg(topic.title, params, y=params.title_y)
        desc_cfg = _build_topic_cfg(topic.description, params, y=params.title_y)
        output_path = os.path.join(out_dir, f"topic_{idx:03d}.mp4")
        svc.apply_topic_title_and_description(
            input_path,
            title_cfg=title_cfg,
            description_cfg=desc_cfg,
            output_path=output_path,
        )
        rel_file = os.path.basename(output_path)
        results.append(TopicsOverlayItem(
            title=topic.title,
            description=topic.description,
            long_description=long_map.get(topic.title),
            output_path=rel_file,
            download_url=f"/content/overlay_download?folder=topics/{overlay_id}&file={rel_file}",
        ))

    return TopicsOverlayResponse(source_path=input_path, results=results)

