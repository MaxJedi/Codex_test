from typing import Any

from openai import OpenAI
import logging
from pathlib import Path
from app.schemas import Segment, Transcript
from app.core.settings import settings

logger = logging.getLogger(__name__)


_SENTINEL = object()

_stt_client: OpenAI | None = None


def _get_stt_client() -> OpenAI:
    global _stt_client
    if _stt_client is None:
        _stt_client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=settings.OPENAI_MAX_RETRIES)
    return _stt_client


def transcribe(audio_path: str) -> Transcript:
    file_path = Path(audio_path)
    resp = _get_stt_client().audio.transcriptions.create(
        model="whisper-1",
        file=file_path,
        response_format="verbose_json",
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )
    logger.info(f"STT response: {resp}")
    segments_payload = _extract_segments(resp)
    segments = [_segment_from_payload(segment) for segment in segments_payload]
    return Transcript(segments=segments)


def _extract_segments(resp: Any):
    segments = getattr(resp, "segments", _SENTINEL)
    if segments is _SENTINEL or segments is None:
        payload = _dump_model(resp)
        if payload is not None:
            segments = payload.get("segments", _SENTINEL)
    if segments is _SENTINEL or segments is None:
        raise ValueError("Transcription response did not include segments.")
    return segments


def _segment_from_payload(segment: Any) -> Segment:
    payload = _dump_model(segment)
    if payload is None:
        payload = {
            "text": getattr(segment, "text"),
            "start": getattr(segment, "start"),
            "end": getattr(segment, "end"),
        }
    return Segment(**payload)


def _dump_model(obj: Any) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return None
