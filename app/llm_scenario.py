import json
from typing import List
from openai import OpenAI
from pydantic import ValidationError
from .schemas import Transcript, Shot, Scenario
from .settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты сценарист коротких вирусных видео. Верни STRICT JSON по схеме Scenario. "
    "Перескажи с локализацией под русскую ЦА 18–35. Без цитирования исходника"
)


def make_ru_scenario(transcript: Transcript, shots: List[Shot], topic: str) -> Scenario:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {"transcript": transcript.model_dump(), "shots": [s.model_dump() for s in shots], "topic": topic},
                ensure_ascii=False,
            ),
        },
    ]
    for attempt in range(2):
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        try:
            data = json.loads(raw)
            return Scenario.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            messages.append(
                {
                    "role": "system",
                    "content": f"Validation error: {e}. Return STRICT JSON matching Scenario schema.",
                }
            )
    raise RuntimeError("Failed to create scenario")
