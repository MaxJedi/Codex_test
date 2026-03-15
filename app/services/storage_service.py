import json
import os
from typing import Any
from datetime import datetime, UTC

from fastapi import UploadFile

from app.core.settings import settings
from app.schemas.carousel import CarouselJobPaths, CarouselJobState, StoredAsset


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def ensure_data_dir(video_id: str) -> str:
    base = os.path.join("data", video_id)
    ensure_dir(base)
    return base


def get_frames_dir(video_id: str) -> str:
    """Return and ensure the persistent directory for extracted frames."""
    base = ensure_data_dir(video_id)
    frames_dir = os.path.join(base, "frames")
    ensure_dir(frames_dir)
    return frames_dir


def save_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_bytes(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


def read_json_if_exists(path: str) -> Any | None:
    if not os.path.exists(path):
        return None
    return read_json(path)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def get_carousels_root() -> str:
    root = os.path.join(settings.DATA_DIR, settings.CAROUSELS_DIRNAME)
    ensure_dir(root)
    return root


def create_carousel_job_dir(job_id: str) -> CarouselJobPaths:
    root = os.path.join(get_carousels_root(), job_id)
    paths = CarouselJobPaths(
        root=root,
        inputs_dir=os.path.join(root, "inputs"),
        intermediate_dir=os.path.join(root, "intermediate"),
        assets_dir=os.path.join(root, "assets"),
        slides_dir=os.path.join(root, "slides"),
        exports_dir=os.path.join(root, "exports"),
        debug_slides_dir=os.path.join(root, "debug_slides"),
    )
    for path in (
        paths.root,
        paths.inputs_dir,
        paths.intermediate_dir,
        paths.assets_dir,
        paths.slides_dir,
        paths.exports_dir,
        paths.debug_slides_dir,
    ):
        ensure_dir(path)
    return paths


def job_file(paths: CarouselJobPaths, *parts: str) -> str:
    return os.path.join(paths.root, *parts)


def save_job_json(paths: CarouselJobPaths, name: str, payload: Any, *, bucket: str = "intermediate") -> str:
    base_dir = getattr(paths, f"{bucket}_dir", None)
    if not isinstance(base_dir, str):
        raise ValueError(f"unknown bucket: {bucket}")
    ensure_dir(base_dir)
    full_path = os.path.join(base_dir, name)
    save_json(full_path, payload)
    return full_path


def build_job_manifest(job_id: str, paths: CarouselJobPaths, *, status: str = "created", current_step: str = "created") -> CarouselJobState:
    now = utc_now_iso()
    return CarouselJobState(
        job_id=job_id,
        status=status,
        current_step=current_step,
        paths=paths,
        created_at=now,
        updated_at=now,
    )


def save_job_status(state: CarouselJobState) -> str:
    state.updated_at = utc_now_iso()
    status_path = os.path.join(state.paths.root, "status.json")
    save_json(status_path, state.model_dump(mode="json"))
    return status_path


def load_job_status(job_id: str) -> CarouselJobState | None:
    status_path = os.path.join(get_carousels_root(), job_id, "status.json")
    raw = read_json_if_exists(status_path)
    if raw is None:
        return None
    return CarouselJobState.model_validate(raw)


def save_job_model(paths: CarouselJobPaths, name: str, model: Any, *, bucket: str = "intermediate") -> str:
    def _to_jsonable(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [_to_jsonable(item) for item in value]
        if isinstance(value, tuple):
            return [_to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): _to_jsonable(item) for key, item in value.items()}
        return value

    payload = _to_jsonable(model)
    return save_job_json(paths, name, payload, bucket=bucket)


async def save_upload(path: str, upload: UploadFile) -> StoredAsset:
    data = await upload.read()
    write_bytes(path, data)
    return StoredAsset(
        name=os.path.basename(path),
        original_name=upload.filename or os.path.basename(path),
        path=path,
        media_type=upload.content_type,
        size_bytes=len(data),
    )


