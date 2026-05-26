from __future__ import annotations

import json
from typing import Any


GLOBAL_TEXT_SYSTEM_PROMPT = (
    "Ты — модуль генерации и редактуры текста для Instagram-каруселей 1080x1350. "
    "Твоя цель: коротко, структурно, без воды, с четкими заголовками и буллетами. "
    "Всегда соблюдай лимиты длины, избегай повторов, не используй токсичный или запрещенный контент. "
    "Выход всегда строго в JSON по указанной схеме. Если есть риск переполнения — перефразируй короче. "
    "После генерации выполняй самопроверку: лимиты, уникальность, ясность, отсутствие двусмысленностей."
)


def build_draft_generation_prompt(*, topic: str, lang: str, slide_count: int) -> str:
    return (
        "SYSTEM: Ты генератор текста карусели. Верни JSON draft_slides[] длиной slide_count. "
        "Каждый элемент: {slide_type, title, bullets[], emphasis_words[], cta}. "
        "Ограничения: title<=70, bullets 3–6, bullet<=90. Язык = lang. "
        "Тематика любая, но формат — карусель с понятными блоками. "
        "Каждый слайд обязан выполнять разную функцию в рамках одной темы: "
        "cover, content, hook, explanation, mistakes, examples, action_steps, checklist, summary, cta."
        "Запрещено повторять одинаковые заголовки, одинаковые буллеты или почти одинаковые формулировки между слайдами. "
        "Слайды должны развивать тему последовательно, а не дублировать друг друга.\n"
        f"INPUT(JSON): {json.dumps({'topic': topic, 'lang': lang, 'slide_count': slide_count}, ensure_ascii=False)}"
    )


def build_compaction_prompt(*, lang: str, slide_count: int, source_text_or_draft_slides: Any) -> str:
    return (
        "SYSTEM: Ты редактор под слайд 1080x1350. Преобразуй draft_slides или user_text в typed_slides[] "
        "со схемой: {id, slide_type, title_block:{text, max_lines, role}, "
        "bullet_blocks:[{text, max_lines, role}], emphasis_spans, cta}. "
        "Строгие ограничения typed_slides: "
        "id только string (например slide_01), "
        "title_block.role только 'title', "
        "bullet_blocks.role только 'bullet', "
        "title_block.max_lines от 1 до 3, "
        "bullet_blocks.max_lines от 1 до 3, "
        "slide_type только из: cover|content|cta|hook|explanation|mistakes|examples|action_steps|checklist|summary. "
        "Не используй role='header' или любые иные значения. "
        "Если строка длинная — перефразируй, сохрани смысл. Верни строго JSON.\n"
        f"INPUT(JSON): {json.dumps({'lang': lang, 'slide_count': slide_count, 'source_text_or_draft_slides': source_text_or_draft_slides}, ensure_ascii=False)}"
    )


def build_self_check_prompt(*, typed_slides: Any) -> str:
    return (
        "SYSTEM: Ты валидатор текста. Проверь ограничения длины, количество пунктов, повторы и ясность. "
        "Особенно проверь, что разные слайды не дублируют друг друга по смыслу, заголовкам и буллетам. "
        "Если есть проблемы — исправь и верни: {typed_slides_checked, issues_fixed:[...], remaining_risks:[...]}. "
        "Никаких пояснений вне JSON.\n"
        f"INPUT(JSON): {json.dumps({'typed_slides': typed_slides}, ensure_ascii=False)}"
    )


def build_user_text_structure_prompt(*, lang: str, slide_count: int, chunks: list[str]) -> str:
    return (
        "SYSTEM: Ты анализатор структуры текста карусели. "
        "Тебе дан plain text, уже разбитый на chunks. "
        "Верни JSON с массивом slide_types длины slide_count, без изменения текста chunks. "
        "slide_type только из: cover|content|cta|hook|explanation|mistakes|examples|action_steps|checklist|summary. "
        "Используй cover для первого и cta для последнего, если не уверен. "
        "Никаких других полей.\n"
        f"INPUT(JSON): {json.dumps({'lang': lang, 'slide_count': slide_count, 'chunks': chunks}, ensure_ascii=False)}"
    )


def build_user_text_draft_prompt(*, lang: str, slide_count: int, user_text: str) -> str:
    return (
        "SYSTEM: Ты редактор структуры пользовательского plain text для карусели. "
        "Верни JSON draft_slides[] длиной slide_count со схемой "
        "{slide_type, title, bullets[], emphasis_words[], cta}. "
        "Сначала попытайся сохранить формулировки максимально близко к исходнику: "
        "разрешено только разбиение по смысловым блокам, выделение заголовков и буллетов. "
        "Не придумывай новые факты. "
        "Если сохранить структуру без правок невозможно — допускаются минимальные изменения текста для соответствия структуре. "
        "slide_type: первый cover, последний cta или summary/cta, остальные content-like. "
        "Верни только JSON.\n"
        f"INPUT(JSON): {json.dumps({'lang': lang, 'slide_count': slide_count, 'user_text': user_text}, ensure_ascii=False)}"
    )
