import json

from openai import OpenAI

from app.core.settings import settings
from app.schemas.topics import TopicIdea


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=settings.OPENAI_MAX_RETRIES)
    return _client


TOPICS_SYSTEM_PROMPT = (
    "Ты креативный продюсер. Сгенерируй N тем для роликов и короткое описание к каждой теме.\n"
    "Формат ответа: STRICT JSON вида {\"topics\": [{\"title\": \"...\", \"description\": \"...\"}, ...]}.\n"
    "Требования:\n"
    "- description: 4-9 слов (русский), без эмодзи.\n"
    "- title: короткий, цепляющий, без клише, до 6-8 слов.\n"
    "- Никаких пояснений, только JSON.\n"
)


def generate_topics(n: int, hint: str | None = None) -> list[TopicIdea]:
    user_prompt = f"Сгенерируй {n} тем."
    if hint:
        user_prompt = f"Тема/контекст: {hint}\nСгенерируй {n} тем."

    resp = _get_client().chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": TOPICS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1,
        response_format={"type": "json_object"},
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    topics = data.get("topics")
    if not isinstance(topics, list):
        return []

    parsed: list[TopicIdea] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not title or not desc:
            continue
        try:
            parsed.append(TopicIdea(title=title, description=desc))
        except Exception:
            continue

    return parsed[:n]

