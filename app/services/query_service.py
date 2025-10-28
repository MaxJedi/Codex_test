import json

from openai import OpenAI

from app.core.settings import settings


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "Ты помощник по формированию поисковых запросов. Преобразуй произвольный пользовательский текст в короткий, точный запрос для поиска релевантных видео на YouTube. "
    "Возвращай STRICT JSON вида {\"query\": \"...\"}. "
    "Требования: \n"
    "- Используй ключевые слова и фразы, убирай лишние вводные слова.\n"
    "- НЕ Добавляй теги.\n"
    "- Не добавляй объяснений, только JSON."
)


def generate_search_query(user_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    resp = _get_client().chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        temperature=1,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return user_text.strip()
    query = str(data.get("query") or user_text).strip()
    return query


