import json
from typing import Literal
from openai import OpenAI
from pydantic import ValidationError
from .schemas import Scenario, Storyboard
from .settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты режиссер монтажа. На основе сценария верни STRICT JSON по схеме Storyboard."
    " Учитывай темп, b-roll и транзишны."
)


def plan_timeline(scn: Scenario, target: Literal["shorts", "youtube"]) -> Storyboard:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"scenario": scn.model_dump(), "target": target}, ensure_ascii=False)},
    ]
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
        return Storyboard.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise RuntimeError(f"Storyboard validation failed: {e}")
