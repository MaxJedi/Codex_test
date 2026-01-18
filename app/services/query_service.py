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


REELS_IDEAS_SYSTEM = (
    "Ты креативный продюсер Instagram Reels. "
    "Сгенерируй N вирусных идей в формате STRICT JSON-мэппинга: "
    "{\"<краткий_заголовок>\": \"<1-2 предложения описания>\" , ...}. "
    "Требования: \n"
    "- Возвращай только JSON без пояснений.\n"
    "- Заголовки короче 10-12 слов, цепляющие, без клише.\n"
    "- Описание — 1-2 предложения, с эмоциональным контекстом и сценографией.\n"
    "- Аудитория: 18-35, язык: ru.\n"
)


def generate_reels_ideas(n: int, topic_hint: str | None = None) -> dict[str, str]:
    prompt = f"Сгенерируй {n} идей." if not topic_hint else f"Тема: {topic_hint}. Сгенерируй {n} идей."
    messages = [
        {"role": "system", "content": REELS_IDEAS_SYSTEM},
        {"role": "user", "content": prompt},
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
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError as e:
        print(f"Failed to parse reels ideas response: {e}")
        pass
    return {}


REEL_PROMPT_SYSTEM = (
    "Ты режиссёр и промпт-инженер. На основе темы и краткого описания сформируй КОРОТКИЙ визуальный промпт для text-to-video модели. "
    "Требования: \n"
    "- Без текста на экране: НИКАКИХ субтитров, надписей, логотипов, водяных знаков. \n"
    "- Вертикальный формат 9:16; мобильная композиция. \n"
    "- Если уместно, персонаж средней возрастной группы (славянской) внешности. ОБЯЗАТЕЛЬНО указать что персонаж славянской внешности в промпте. .\n"
    "- Эмоциональный, кинематографичный, реалистичный свет. \n"
    "- Кратко (<= 600 символов), только чистое текстовое описание сцены/движения и атмосферы; БЕЗ лишних пояснений. "
    "- Сцена должна быть короткой, статичной, в ней должен быть один объект или персонаж. Может быть объект на фоне природных явлений, космических объектов, фентези или фантастических пейзажей."
)


def generate_reel_visual_prompt(title: str, description: str | None = None) -> str:
    """Ask GPT to produce a concise visual prompt for the given reel idea."""
    user_payload = {"title": title}
    if description:
        user_payload["description"] = description
    messages = [
        {"role": "system", "content": REEL_PROMPT_SYSTEM},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    resp = _get_client().chat.completions.create(
        model="gpt-5-mini",
        messages=messages,
        temperature=1,
    )
    text = resp.choices[0].message.content.strip()
    # Clamp length defensively
    if len(text) > 600:
        text = text[:599] + "…"
    return text


