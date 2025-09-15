from typing import Any

from openai import OpenAI

from .schemas import Segment, Transcript
from .settings import settings


_SENTINEL = object()

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def transcribe(audio_path: str) -> Transcript:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )
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
