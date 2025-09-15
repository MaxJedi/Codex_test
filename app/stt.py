import logging
from typing import Any, Iterable
from openai import OpenAI
from .settings import settings
from .schemas import Transcript, Segment

logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_API_KEY)


def transcribe(audio_path: str) -> Transcript:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )
    segments_data = _extract_segments(resp)
    segments = [Segment(text=s["text"], start=s["start"], end=s["end"]) for s in segments_data]
    logger.debug("Transcribed %s segments from %s", len(segments), audio_path)
    return Transcript(segments=segments)


def _extract_segments(resp: Any) -> Iterable[dict[str, Any]]:
    if hasattr(resp, "segments") and resp.segments is not None:
        return [_normalise_segment(seg) for seg in resp.segments]
    if hasattr(resp, "model_dump"):
        data = resp.model_dump()
    else:
        data = dict(resp)
    segments = data.get("segments")
    if not segments:
        raise RuntimeError("OpenAI transcription response is missing segments")
    return [_normalise_segment(seg) for seg in segments]


def _normalise_segment(segment: Any) -> dict[str, Any]:
    if hasattr(segment, "model_dump"):
        data = segment.model_dump()
    elif isinstance(segment, dict):
        data = segment
    else:
        data = segment.__dict__
    for key in ("text", "start", "end"):
        if key not in data:
            raise RuntimeError(f"Transcription segment missing '{key}' field")
    return {"text": data["text"], "start": float(data["start"]), "end": float(data["end"]) }
