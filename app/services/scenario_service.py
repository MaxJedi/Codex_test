import json
from re import S
from typing import List
from openai import OpenAI
import httpx
from pydantic import ValidationError
from app.schemas import Transcript, Shot, Scenario, KeyObject
from app.core.settings import settings
import logging
import os
from app.services.storage_service import save_json, ensure_dir

logger = logging.getLogger(__name__)

_llm_client: OpenAI | None = None


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=settings.OPENAI_MAX_RETRIES)
    return _llm_client

SYSTEM_PROMPT = (
    "Ты сценарист коротких вирусных видео. Верни prompt-запрос для генерации видео с описанием каждой сцены, действиями в сцене и диалогами. "
    "Каждая сцена должна длиться 5–10 секунд. "
    "Перескажи сюжет, локализуя его под русскоязычную аудиторию 18–35 лет. "
    "Соблюдай стиль контента такой же, как в оригинальном видео (реалистичный, мультяшный, киношный, формат TikTok/Shorts и т.д.). "
    "Сохраняй жанр и формат видео такими же, как у исходника (например, юмор, мотивация, интервью, скетч, storytelling и др.). "
    "Текстовые описания сцен (визуальные prompts) дай на языке, который модель понимает лучше всего (английский), а диалоги в сценах приведи на русском языке — это обеспечит понятность модели и одновременно сохранит локализацию под РФ. "
    "Учти, что для генерации используются разные модели (Pika, RunwayML, Sora и др.), поэтому твой prompt должен быть универсальным и эффективно интерпретироваться любой из них:contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}. "
    "Если в оригинальном видео были явно выражены ключевые объекты, лица или эмоции, подчеркни их присутствие и значение при описании соответствующих сцен. "
    "Без прямого цитирования исходника. Формат ответа: STRICT JSON со сценами scene_1, scene_2, scene_3, ... — в каждом объекте сцены указать текстовый промпт и диалог."
)

def make_ru_scenario(transcript: Transcript, shots: List[Shot], topic: str, key_objects: List[KeyObject]) -> Scenario:
    visual_hints = {
        "shots": [s.model_dump() for s in shots],
        "key_objects": [k.model_dump() for k in key_objects],
    }
    
    logger.info(f"Visual hints: {visual_hints}")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {"transcript": transcript.model_dump(), "visual_hints": visual_hints, "topic": topic},
                ensure_ascii=False,
            ),
        },
    ]   
    out_dir = os.path.join("data", "scenario")
    ensure_dir(out_dir)
    save_json(os.path.join(out_dir, "scenario_messages.json"), messages)
    logger.info(f"Scenario messages: {messages}")
    for attempt in range(2):
        resp = _get_llm_client().chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            temperature=1,
            response_format={"type": "json_object"},
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        logger.info(f"Scenario data: {data}")
        save_json(os.path.join(out_dir, "scenario_data.json"), data)
        return data

