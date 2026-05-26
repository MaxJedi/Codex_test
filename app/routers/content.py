import json
import logging
import mimetypes
import os
import subprocess
import threading
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
    ApprovalSubmitRequest,
    CarouselCreateRequest,
    ReferenceAssets,
    StoredAsset,
    StyleVars,
)
from app.services.carousel_job_service import CarouselJobService
from app.services.font_registry import list_carousel_font_options, resolve_carousel_font_file
from app.services.text_overlay_service import TextOverlayService
from app.services.storage_service import (
    can_delete_carousel_job,
    cleanup_expired_carousel_jobs,
    create_carousel_job_dir,
    delete_carousel_job,
    ensure_dir,
    load_job_status,
    save_upload,
)
from app.services.topics_service import generate_topics, generate_long_descriptions


router = APIRouter(prefix="/content", tags=["content"])
carousel_job_service = CarouselJobService()
logger = logging.getLogger(__name__)
_session_jobs_lock = threading.Lock()
_session_jobs: dict[str, set[str]] = {}


def _prune_deleted_jobs_from_sessions() -> None:
    with _session_jobs_lock:
        empty_sessions = [session_id for session_id, job_ids in _session_jobs.items() if not job_ids]
        for session_id in empty_sessions:
            _session_jobs.pop(session_id, None)


def _cleanup_session_jobs(session_id: str) -> list[str]:
    with _session_jobs_lock:
        job_ids = set(_session_jobs.pop(session_id, set()))
    deleted: list[str] = []
    for job_id in job_ids:
        if not can_delete_carousel_job(job_id):
            with _session_jobs_lock:
                _session_jobs.setdefault(session_id, set()).add(job_id)
            continue
        if delete_carousel_job(job_id):
            deleted.append(job_id)
    return deleted


def _register_session_job(session_id: str, job_id: str) -> None:
    with _session_jobs_lock:
        _session_jobs.setdefault(session_id, set()).add(job_id)


def _safe_realpath(path: str) -> str:
    root = os.path.realpath(settings.FILE_BROWSER_ROOT)
    real = os.path.realpath(path)
    if not real.startswith(root.rstrip(os.sep) + os.sep) and real != root:
        raise HTTPException(403, f"path is outside FILE_BROWSER_ROOT: {settings.FILE_BROWSER_ROOT}")
    return real


def _carousel_download_url(job_id: str, relative_path: str) -> str:
    return f"/content/carousel/{job_id}/download/{relative_path}"


def _safe_job_file(job_id: str, relative_path: str) -> tuple[object, str]:
    state = load_job_status(job_id)
    if state is None:
        raise HTTPException(404, "Carousel job not found")
    root = os.path.realpath(state.paths.root)
    full = os.path.realpath(os.path.join(root, relative_path))
    if not full.startswith(root.rstrip(os.sep) + os.sep):
        raise HTTPException(403, "Invalid file path")
    if not os.path.isfile(full):
        raise HTTPException(404, "File not found")
    return state, full


def _serialize_carousel_outputs(job_id: str, outputs: dict | None) -> dict | None:
    if outputs is None:
        return None
    slide_paths = outputs.get("slide_paths") or []
    return {
        **outputs,
        "slide_items": [
            {"path": path, "url": _carousel_download_url(job_id, path)}
            for path in slide_paths
        ],
        "preview_strip_url": _carousel_download_url(job_id, outputs["preview_strip_path"]) if outputs.get("preview_strip_path") else None,
        "job_spec_url": _carousel_download_url(job_id, outputs["job_spec_path"]) if outputs.get("job_spec_path") else None,
        "zip_url": _carousel_download_url(job_id, outputs["zip_path"]) if outputs.get("zip_path") else None,
    }


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


@router.get("/carousel/fonts")
def carousel_list_fonts():
    fonts = list_carousel_font_options()
    logger.info("carousel.fonts: listed count=%s", len(fonts))
    return {
        "fonts": [item.model_dump() for item in fonts],
        "auto_label": "Любой",
        "auto_value": "AUTO",
    }


@router.get("/carousel/fonts/{filename}")
def carousel_font_file(filename: str):
    font_path = resolve_carousel_font_file(filename)
    if not font_path:
        logger.warning("carousel.fonts: file not found filename=%s", filename)
        raise HTTPException(404, "Font file not found")
    media_type = mimetypes.guess_type(font_path)[0] or "application/octet-stream"
    return FileResponse(font_path, media_type=media_type, filename=os.path.basename(font_path))


@router.post("/carousel/jobs")
async def carousel_create_job(
    topic: str = Form(""),
    lang: str = Form("auto"),
    slide_count: int = Form(7),
    user_text: str = Form(""),
    style_vars_json: str = Form("{}"),
    session_id: str = Form(""),
    ref_style_images: UploadFile | list[UploadFile] | None = File(None),
    subject_image: UploadFile | None = File(None),
    brand_assets: UploadFile | list[UploadFile] | None = File(None),
):
    logger.info("carousel.create_job: request received topic=%r lang=%s slide_count=%s", topic, lang, slide_count)
    ttl_deleted = cleanup_expired_carousel_jobs(settings.CAROUSEL_JOB_TTL_SECONDS)
    if ttl_deleted:
        logger.info("carousel.create_job: ttl cleanup removed=%s", len(ttl_deleted))
    _prune_deleted_jobs_from_sessions()
    normalized_session_id = session_id.strip()
    if normalized_session_id:
        deleted_session_jobs = _cleanup_session_jobs(normalized_session_id)
        if deleted_session_jobs:
            logger.info(
                "carousel.create_job: session cleanup session_id=%s removed=%s",
                normalized_session_id,
                len(deleted_session_jobs),
            )
    try:
        style_vars_data = json.loads(style_vars_json or "{}")
    except json.JSONDecodeError:
        logger.warning("carousel.create_job: invalid style_vars_json")
        raise HTTPException(400, "Invalid JSON in style_vars_json")

    payload = CarouselCreateRequest.model_validate(
        {
            "topic": topic,
            "lang": lang,
            "slide_count": slide_count,
            "user_text": user_text or None,
            "style_vars": StyleVars.model_validate(style_vars_data),
        }
    )

    job_id = f"carousel_{uuid.uuid4().hex[:12]}"
    paths = create_carousel_job_dir(job_id)

    ref_uploads = ref_style_images if isinstance(ref_style_images, list) else ([ref_style_images] if ref_style_images else [])
    brand_uploads = brand_assets if isinstance(brand_assets, list) else ([brand_assets] if brand_assets else [])

    ref_assets_saved: list[StoredAsset] = []
    for idx, upload in enumerate(ref_uploads[:5], start=1):
        ext = os.path.splitext(upload.filename or "")[1] or ".png"
        target = os.path.join(paths.inputs_dir, f"ref_style_{idx:02d}{ext}")
        ref_assets_saved.append(await save_upload(target, upload))

    subject_saved = None
    if subject_image and subject_image.filename:
        ext = os.path.splitext(subject_image.filename or "")[1] or ".png"
        target = os.path.join(paths.inputs_dir, f"subject{ext}")
        subject_saved = await save_upload(target, subject_image)

    brand_saved: list[StoredAsset] = []
    for idx, upload in enumerate(brand_uploads, start=1):
        ext = os.path.splitext(upload.filename or "")[1] or ".bin"
        target = os.path.join(paths.inputs_dir, f"brand_{idx:02d}{ext}")
        brand_saved.append(await save_upload(target, upload))

    assets = ReferenceAssets(
        ref_style_images=ref_assets_saved,
        subject_image=subject_saved,
        brand_assets=brand_saved,
    )
    response = carousel_job_service.create_job(payload, assets, job_id=job_id)
    if normalized_session_id:
        _register_session_job(normalized_session_id, job_id)
    logger.info(
        "carousel.create_job: created job_id=%s refs=%s subject=%s brand_assets=%s",
        job_id,
        len(ref_assets_saved),
        bool(subject_saved),
        len(brand_saved),
    )
    return response.model_dump(mode="json")


@router.post("/carousel/session/end")
def carousel_session_end(payload: dict):
    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        raise HTTPException(400, "session_id required")
    deleted_job_ids = _cleanup_session_jobs(session_id)
    logger.info(
        "carousel.session_end: session_id=%s removed=%s",
        session_id,
        len(deleted_job_ids),
    )
    return {"ok": True, "deleted_job_ids": deleted_job_ids}


@router.post("/carousel/{job_id}/draft")
def carousel_generate_draft(job_id: str):
    logger.info("carousel.generate_draft: start job_id=%s", job_id)
    try:
        response = carousel_job_service.generate_draft(job_id)
    except FileNotFoundError as exc:
        logger.warning("carousel.generate_draft: job not found job_id=%s", job_id)
        raise HTTPException(404, str(exc)) from exc
    except Exception:
        logger.exception("carousel.generate_draft: failed job_id=%s", job_id)
        raise
    logger.info("carousel.generate_draft: done job_id=%s", job_id)
    return response.model_dump(mode="json")


@router.post("/carousel/{job_id}/approve")
def carousel_approve(job_id: str, payload: ApprovalSubmitRequest):
    logger.info("carousel.approve: start job_id=%s slides=%s", job_id, len(payload.slides))
    try:
        response = carousel_job_service.approve(job_id, payload)
    except FileNotFoundError as exc:
        logger.warning("carousel.approve: job not found job_id=%s", job_id)
        raise HTTPException(404, str(exc)) from exc
    except Exception:
        logger.exception("carousel.approve: failed job_id=%s", job_id)
        raise
    logger.info("carousel.approve: done job_id=%s", job_id)
    return response.model_dump(mode="json")


@router.post("/carousel/{job_id}/render")
def carousel_render(job_id: str):
    logger.info("carousel.render: start job_id=%s", job_id)
    try:
        response = carousel_job_service.render(job_id)
    except FileNotFoundError as exc:
        logger.warning("carousel.render: job not found job_id=%s", job_id)
        raise HTTPException(404, str(exc)) from exc
    except Exception:
        logger.exception("carousel.render: failed job_id=%s", job_id)
        raise
    payload = response.model_dump(mode="json")
    payload["outputs"] = _serialize_carousel_outputs(job_id, payload.get("outputs"))
    logger.info("carousel.render: done job_id=%s slides=%s", job_id, len(payload.get("outputs", {}).get("slide_paths", [])))
    return payload


@router.get("/carousel/{job_id}")
def carousel_get_job(job_id: str):
    logger.info("carousel.get_job: job_id=%s", job_id)
    try:
        detail = carousel_job_service.get_job_detail(job_id)
    except FileNotFoundError as exc:
        logger.warning("carousel.get_job: job not found job_id=%s", job_id)
        raise HTTPException(404, str(exc)) from exc
    payload = detail.model_dump(mode="json")
    payload["outputs"] = _serialize_carousel_outputs(job_id, payload.get("outputs"))
    return payload


@router.get("/carousel/{job_id}/download/{file_path:path}")
def carousel_download(job_id: str, file_path: str):
    logger.info("carousel.download: job_id=%s file=%s", job_id, file_path)
    _, full = _safe_job_file(job_id, file_path)
    media_type, _ = mimetypes.guess_type(full)
    return FileResponse(full, media_type=media_type or "application/octet-stream", filename=os.path.basename(full))

