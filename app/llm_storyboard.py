import json
import logging
from typing import Literal
from openai import OpenAI
from pydantic import ValidationError
from .schemas import Scenario, Storyboard
from .settings import settings

logger = logging.getLogger(__name__)
client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты режиссер монтажа. На основе сценария верни STRICT JSON по схеме Storyboard."
    " Учитывай темп, b-roll и транзишны. Убедись, что суммарная длительность соответствует целевому формату."
)


def plan_timeline(scn: Scenario, target: Literal["shorts", "youtube"]) -> Storyboard:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"scenario": scn.model_dump(), "target": target}, ensure_ascii=False)},
    ]
    for attempt in range(2):
        resp = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        try:
            data = json.loads(raw)
            board = Storyboard.model_validate(data)
            duration = board.total_duration_sec
            if target == "shorts" and not (45 <= duration <= 60):
                raise ValueError("Shorts storyboard duration must be 45-60 seconds")
            if target == "youtube" and not (60 <= duration <= 120):
                raise ValueError("YouTube storyboard duration must be 60-120 seconds")
            return board
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("Storyboard validation attempt %s failed: %s", attempt + 1, e)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Validation error: {err}. Верни STRICT JSON по схеме Storyboard, "
                        "учти длительность {target} формата."
                    ).format(err=e, target=target),
                }
            )
    raise RuntimeError("Failed to create storyboard")
