from openai import OpenAI
from .settings import settings
from .schemas import Transcript, Segment

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def transcribe(audio_path: str) -> Transcript:
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )
    segments = [Segment(text=s["text"], start=s["start"], end=s["end"]) for s in resp["segments"]]
    return Transcript(segments=segments)
