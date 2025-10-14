import json
from typing import Literal
from openai import OpenAI
from pydantic import ValidationError
from app.schemas import Scenario, Storyboard
from app.core.settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты режиссёр монтажа. На основе сценария верни STRICT JSON по схеме Storyboard. "
    "Учитывай темп, использование b-roll и тип переходов (transitions) так же, как в оригинальном видео. "
    "Придерживайся того же стиля монтажа, что и у исходника (например, быстрый клиповый монтаж в стиле TikTok или плавные кинематографичные переходы). "
    "Если оригинальное видео делало акцент на определённых объектах, лицах или эмоциях, отрази это в раскадровке (например, отдельные крупные планы или вставки этих элементов). "
    "Учти возможные ограничения генерации видео: например, максимальная длительность одной сцены около 10 секунд, ограничение на сложность переходов и т.д., и адаптируй монтаж под эти ограничения."
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
