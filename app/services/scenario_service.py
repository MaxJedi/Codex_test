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
    "Ты сценарист коротких вирусных видео. Верни promt запрос для генерации видео с описанием каждой сцены, действий в сцене и диалогов в сцене. Каждая сцена должна длиться 5-10 секунд. "
    "Перескажи с локализацией под русскую ЦА 18–35. Без цитирования исходника."
    "Формат ответа: STRICT JSON по схеме scene_1, scene_2, scene_3, ...в каждом объекте сцены текстовый промпт и диалог в сцене."
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

