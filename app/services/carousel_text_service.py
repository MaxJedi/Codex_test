from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from app.core.settings import settings
from app.schemas.carousel import (
    ApprovalPayload,
    ApprovalSlide,
    CarouselCreateRequest,
    CarouselJobConfig,
    DraftSlide,
    EditRules,
    SafeMargins,
    TextBlock,
    TypedSlide,
    TypedSlidesReview,
)
from app.services.prompts.carousel_text_prompts import (
    GLOBAL_TEXT_SYSTEM_PROMPT,
    build_compaction_prompt,
    build_draft_generation_prompt,
    build_self_check_prompt,
)


_client: OpenAI | None = None
logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
    return _client


def _coalesce_lang(lang: str) -> str:
    return "ru" if lang == "auto" else lang


def _call_json_llm(system_prompt: str, user_prompt: str) -> dict:
    logger.info("carousel.text.llm: request start")
    resp = _get_client().chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=1,
        response_format={"type": "json_object"},
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )
    raw = resp.choices[0].message.content or "{}"
    logger.info("carousel.text.llm: response received chars=%s", len(raw))
    return json.loads(raw)


def _clean_line(value: str, *, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    if len(value) <= max_chars:
        return value
    shortened = value[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return (shortened or value[: max_chars - 1]).rstrip(" ,;:-") + "…"


def _split_user_text(user_text: str, slide_count: int) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", user_text) if chunk.strip()]
    if not chunks:
        chunks = [line.strip() for line in user_text.splitlines() if line.strip()]
    if not chunks:
        chunks = [user_text.strip()]
    if len(chunks) >= slide_count:
        return chunks[:slide_count]

    words = user_text.split()
    if not words:
        return [""] * slide_count
    slice_size = max(8, len(words) // max(1, slide_count))
    built: list[str] = []
    for idx in range(0, len(words), slice_size):
        built.append(" ".join(words[idx: idx + slice_size]))
    return (built or chunks)[:slide_count]


def _normalize_text_signature(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _topic_terms(topic: str) -> list[str]:
    terms = [_normalize_text_signature(part) for part in topic.split()]
    return [term for term in terms if len(term) > 2]


def _coerce_text_role(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip().lower()
    if normalized in {"header", "heading"}:
        return "title"
    allowed = {"title", "bullet", "caption", "cta", "subtitle"}
    return normalized if normalized in allowed else fallback


def _normalize_llm_typed_item(item: object, *, index: int, slide_count: int) -> dict:
    if not isinstance(item, dict):
        return {}
    slide_type = item.get("slide_type")
    if not isinstance(slide_type, str):
        slide_type = "cover" if index == 1 else ("cta" if index == slide_count else "content")

    title_block_raw = item.get("title_block")
    title_block = title_block_raw if isinstance(title_block_raw, dict) else {}
    bullet_blocks_raw = item.get("bullet_blocks")
    bullet_blocks_list = bullet_blocks_raw if isinstance(bullet_blocks_raw, list) else []

    normalized_bullet_blocks: list[dict] = []
    for block in bullet_blocks_list:
        if not isinstance(block, dict):
            continue
        normalized_bullet_blocks.append(
            {
                "text": str(block.get("text", "")).strip(),
                "max_lines": int(block.get("max_lines", 3) or 3),
                "role": _coerce_text_role(block.get("role"), fallback="bullet"),
            }
        )

    return {
        "id": str(item.get("id") or f"slide_{index:02d}"),
        "slide_type": slide_type,
        "title_block": {
            "text": str(title_block.get("text", "")).strip(),
            "max_lines": int(title_block.get("max_lines", 3 if index == 1 else 2) or (3 if index == 1 else 2)),
            "role": _coerce_text_role(title_block.get("role"), fallback="title"),
        },
        "bullet_blocks": normalized_bullet_blocks[:6],
        "emphasis_spans": [str(item_text) for item_text in (item.get("emphasis_spans") or [])][:12],
        "cta": str(item.get("cta")).strip() if item.get("cta") is not None else None,
    }


def _has_low_diversity_draft(slides: list[DraftSlide]) -> bool:
    if len(slides) < 3:
        return False
    title_signatures = {_normalize_text_signature(slide.title) for slide in slides if slide.title.strip()}
    bullet_signatures = [
        _normalize_text_signature(block)
        for slide in slides
        for block in slide.bullets
        if block.strip()
    ]
    unique_bullets = {item for item in bullet_signatures if item}
    if len(title_signatures) <= max(2, len(slides) // 2):
        return True
    if bullet_signatures and len(unique_bullets) <= max(3, len(bullet_signatures) // 2):
        return True
    return False


def _has_low_diversity_typed(slides: list[TypedSlide]) -> bool:
    if len(slides) < 3:
        return False
    title_signatures = {_normalize_text_signature(slide.title_block.text) for slide in slides if slide.title_block.text.strip()}
    bullet_signatures = [
        _normalize_text_signature(block.text)
        for slide in slides
        for block in slide.bullet_blocks
        if block.text.strip()
    ]
    unique_bullets = {item for item in bullet_signatures if item}
    return len(title_signatures) <= max(2, len(slides) // 2) or (
        bullet_signatures and len(unique_bullets) <= max(3, len(bullet_signatures) // 2)
    )


def _structured_slide_plan(lang: str) -> list[tuple[str, str, str]]:
    if _coalesce_lang(lang) == "ru":
        return [
            ("cover", "О чем этот разбор", "Коротко вводит в тему и обещает пользу"),
            ("content", "Почему тема важна", "Объясняет значимость темы и контекст"),
            ("content", "Главная ошибка", "Показывает частую ошибку или ложный подход"),
            ("content", "Как это распознать", "Дает признаки, симптомы или маркеры"),
            ("content", "Из-за чего это происходит", "Разбирает причины и внутреннюю механику"),
            ("content", "Что делать на практике", "Дает пошаговые действия и применимые советы"),
            ("content", "На что обратить внимание", "Добавляет нюансы, ограничения и акценты"),
            ("content", "Пример или сценарий", "Показывает тему на понятном кейсе"),
            ("content", "Краткий чек-лист", "Сводит идеи в компактную памятку"),
            ("cta", "Что сделать дальше", "Закрывает карусель действием и выводом"),
        ]
    return [
        ("cover", "What this carousel is about", "Introduces the topic and promise"),
        ("content", "Why it matters", "Explains the relevance and context"),
        ("content", "The main mistake", "Shows a common wrong approach"),
        ("content", "How to spot it", "Gives signals and markers"),
        ("content", "Why it happens", "Explains causes and mechanics"),
        ("content", "What to do instead", "Provides practical actions"),
        ("content", "What to watch closely", "Adds nuance and caveats"),
        ("content", "Example or scenario", "Grounds the idea in a concrete case"),
        ("content", "Quick checklist", "Summarizes into a compact checklist"),
        ("cta", "What to do next", "Closes with action"),
    ]


def _build_structured_draft_slides(topic: str, lang: str, slide_count: int) -> list[DraftSlide]:
    resolved_lang = _coalesce_lang(lang)
    topic_label = topic.strip() or ("эта тема" if resolved_lang == "ru" else "this topic")
    topic_words = _topic_terms(topic_label)
    anchor = topic_words[0] if topic_words else ("тема" if resolved_lang == "ru" else "topic")
    plan = _structured_slide_plan(lang)
    selected = plan[:slide_count] if slide_count <= len(plan) else plan + [plan[-2]] * (slide_count - len(plan))

    slides: list[DraftSlide] = []
    for idx, (slide_type, heading, intent) in enumerate(selected, start=1):
        if resolved_lang == "ru":
            if slide_type == "cover":
                title = _clean_line(topic_label, max_chars=70)
                bullets = [
                    _clean_line(f"Разбираем тему: {topic_label}", max_chars=90),
                    _clean_line("Покажем ключевые идеи без воды и повторов", max_chars=90),
                    _clean_line("Дойдем до понятных выводов и действий", max_chars=90),
                ]
                cta = None
            elif slide_type == "cta":
                title = heading
                bullets = [
                    _clean_line(f"Выберите 1 вывод по теме «{topic_label}»", max_chars=90),
                    _clean_line("Сохраните карусель как короткую памятку", max_chars=90),
                    _clean_line("Вернитесь к ней, когда будете применять советы", max_chars=90),
                ]
                cta = "Сохраните карусель и вернитесь к ней позже"
            else:
                title = _clean_line(f"{heading}: {topic_label}", max_chars=70)
                bullets = [
                    _clean_line(f"{intent} применительно к теме «{topic_label}».", max_chars=90),
                    _clean_line(f"Покажите отдельный аспект, а не повторяйте прошлый слайд про {anchor}.", max_chars=90),
                    _clean_line(f"Дайте новый практический тезис, связанный с темой «{topic_label}».", max_chars=90),
                ]
                cta = None
            emphasis_words = [word for word in topic_label.split()[:2] if len(word) > 2][:4]
        else:
            if slide_type == "cover":
                title = _clean_line(topic_label, max_chars=70)
                bullets = [
                    _clean_line(f"We unpack the topic: {topic_label}", max_chars=90),
                    _clean_line("The slides stay practical, short and non-repetitive", max_chars=90),
                    _clean_line("You get clear takeaways and action points", max_chars=90),
                ]
                cta = None
            elif slide_type == "cta":
                title = heading
                bullets = [
                    _clean_line(f"Choose one next step connected to {topic_label}", max_chars=90),
                    _clean_line("Save the carousel as a quick reference", max_chars=90),
                    _clean_line("Come back when you are ready to apply it", max_chars=90),
                ]
                cta = "Save this carousel for later"
            else:
                title = _clean_line(f"{heading}: {topic_label}", max_chars=70)
                bullets = [
                    _clean_line(f"{intent} in the context of {topic_label}.", max_chars=90),
                    _clean_line(f"Cover a new angle instead of repeating the previous slide about {anchor}.", max_chars=90),
                    _clean_line(f"Add one more practical point tied to {topic_label}.", max_chars=90),
                ]
                cta = None
            emphasis_words = [word for word in topic_label.split()[:2] if len(word) > 2][:4]

        slides.append(
            DraftSlide(
                slide_type=slide_type,
                title=title,
                bullets=bullets,
                emphasis_words=emphasis_words,
                cta=cta,
            )
        )
    return slides


def _fallback_draft_slides(topic: str, lang: str, slide_count: int) -> list[DraftSlide]:
    return _build_structured_draft_slides(topic=topic, lang=lang, slide_count=slide_count)


def _draft_from_user_text(user_text: str, lang: str, slide_count: int) -> list[DraftSlide]:
    chunks = _split_user_text(user_text, slide_count)
    slides: list[DraftSlide] = []
    for idx in range(slide_count):
        chunk = chunks[idx] if idx < len(chunks) else chunks[-1]
        lines = [line.strip(" -•") for line in re.split(r"[.\n]", chunk) if line.strip()]
        title = _clean_line(lines[0] if lines else chunk, max_chars=70)
        bullets = [_clean_line(line, max_chars=90) for line in lines[1:4]]
        if not bullets:
            bullets = [
                _clean_line(chunk, max_chars=90),
                "Ключевая мысль без лишних слов" if _coalesce_lang(lang) == "ru" else "One clear take-away",
            ]
        slides.append(
            DraftSlide(
                slide_type="cover" if idx == 0 else ("cta" if idx == slide_count - 1 else "content"),
                title=title,
                bullets=bullets[:6],
                emphasis_words=[word for word in title.split()[:2] if len(word) > 3][:4],
                cta="Сохраните этот разбор" if idx == slide_count - 1 and _coalesce_lang(lang) == "ru" else None,
            )
        )
    return slides


def _fallback_compaction(source_slides: list[DraftSlide]) -> list[TypedSlide]:
    typed: list[TypedSlide] = []
    for idx, slide in enumerate(source_slides, start=1):
        typed.append(
            TypedSlide(
                id=f"slide_{idx:02d}",
                slide_type=slide.slide_type,
                title_block=TextBlock(
                    text=_clean_line(slide.title, max_chars=70),
                    max_lines=3 if slide.slide_type == "cover" else 2,
                    role="title",
                ),
                bullet_blocks=[
                    TextBlock(text=_clean_line(item, max_chars=90), max_lines=3, role="bullet")
                    for item in slide.bullets[:6]
                ],
                emphasis_spans=slide.emphasis_words[:12],
                cta=_clean_line(slide.cta, max_chars=90) if slide.cta else None,
            )
        )
    return typed


def _deterministic_self_check(typed_slides: list[TypedSlide]) -> TypedSlidesReview:
    fixed: list[TypedSlide] = []
    issues_fixed: list[str] = []
    remaining_risks: list[str] = []
    seen_titles: set[str] = set()

    for slide in typed_slides:
        title = _clean_line(slide.title_block.text, max_chars=70)
        if title != slide.title_block.text:
            issues_fixed.append(f"{slide.id}: укорочен заголовок")
        if title.lower() in seen_titles:
            title = _clean_line(f"{title} {slide.id[-2:]}", max_chars=70)
            issues_fixed.append(f"{slide.id}: заголовок сделан уникальным")
        seen_titles.add(title.lower())

        bullet_blocks = slide.bullet_blocks[:6]
        if len(bullet_blocks) != len(slide.bullet_blocks):
            issues_fixed.append(f"{slide.id}: обрезаны лишние буллеты")
        normalized_bullets = []
        for block in bullet_blocks:
            normalized = _clean_line(block.text, max_chars=90)
            if normalized != block.text:
                issues_fixed.append(f"{slide.id}: укорочен буллет")
            normalized_bullets.append(block.model_copy(update={"text": normalized}))
        if slide.slide_type != "cta" and not normalized_bullets:
            remaining_risks.append(f"{slide.id}: мало текста для контентного слайда")

        fixed.append(
            slide.model_copy(
                update={
                    "title_block": slide.title_block.model_copy(update={"text": title}),
                    "bullet_blocks": normalized_bullets,
                    "emphasis_spans": slide.emphasis_spans[:12],
                    "cta": _clean_line(slide.cta, max_chars=90) if slide.cta else None,
                }
            )
        )
    return TypedSlidesReview(
        typed_slides_checked=fixed,
        issues_fixed=issues_fixed,
        remaining_risks=remaining_risks,
    )


def _enforce_slide_diversity(typed_slides: list[TypedSlide], *, topic: str, lang: str) -> tuple[list[TypedSlide], list[str]]:
    issues_fixed: list[str] = []
    if not _has_low_diversity_typed(typed_slides):
        return typed_slides, issues_fixed

    diversified_source = _build_structured_draft_slides(
        topic=topic,
        lang=lang,
        slide_count=len(typed_slides),
    )
    diversified_typed = _fallback_compaction(diversified_source)

    merged: list[TypedSlide] = []
    for original, replacement in zip(typed_slides, diversified_typed, strict=False):
        original_title = _normalize_text_signature(original.title_block.text)
        original_bullets = [_normalize_text_signature(block.text) for block in original.bullet_blocks]
        if original_title and original_bullets and (original_title == replacement.title_block.text.lower() or len(set(original_bullets)) <= 1):
            merged.append(replacement.model_copy(update={"id": original.id}))
            issues_fixed.append(f"{original.id}: заменен повторяющийся слайд")
        else:
            merged.append(original)

    if _has_low_diversity_typed(merged):
        return diversified_typed, issues_fixed + ["Низкое разнообразие слайдов: применен structured fallback"]
    return merged, issues_fixed


class CarouselTextService:
    def build_job_config(
        self,
        payload: CarouselCreateRequest,
        *,
        ref_count: int,
        has_subject_image: bool,
    ) -> CarouselJobConfig:
        style_vars = payload.style_vars
        config = CarouselJobConfig(
            lang=_coalesce_lang(payload.lang),
            slide_count=payload.slide_count,
            has_user_text=bool((payload.user_text or "").strip()),
            has_subject_image=has_subject_image,
            ref_count=ref_count,
            output_format=style_vars.export_format,
            safe_margins=SafeMargins(
                top=style_vars.safe_top,
                bottom=style_vars.safe_bottom,
                left=style_vars.safe_left,
                right=style_vars.safe_right,
            ),
            style_vars=style_vars,
        )
        logger.info(
            "carousel.text.config: built lang=%s slide_count=%s has_user_text=%s ref_count=%s has_subject=%s",
            config.lang,
            config.slide_count,
            config.has_user_text,
            config.ref_count,
            config.has_subject_image,
        )
        return config

    def generate_draft_slides(self, *, topic: str, lang: str, slide_count: int) -> list[DraftSlide]:
        logger.info("carousel.text.draft: generating topic=%r lang=%s slide_count=%s", topic, lang, slide_count)
        prompt = build_draft_generation_prompt(topic=topic, lang=_coalesce_lang(lang), slide_count=slide_count)
        try:
            data = _call_json_llm(GLOBAL_TEXT_SYSTEM_PROMPT, prompt)
            items = data.get("draft_slides", [])
            slides = [DraftSlide.model_validate(item) for item in items]
            if len(slides) == slide_count and not _has_low_diversity_draft(slides):
                logger.info("carousel.text.draft: llm result accepted count=%s", len(slides))
                return slides
            logger.warning(
                "carousel.text.draft: llm result rejected count=%s low_diversity=%s",
                len(slides),
                _has_low_diversity_draft(slides),
            )
        except Exception:
            logger.exception("carousel.text.draft: llm generation failed, using fallback")
        logger.info("carousel.text.draft: using deterministic fallback")
        return _fallback_draft_slides(topic=topic, lang=lang, slide_count=slide_count)

    def build_source_draft_slides(
        self,
        *,
        topic: str,
        lang: str,
        slide_count: int,
        user_text: str | None,
    ) -> list[DraftSlide]:
        if user_text and user_text.strip():
            logger.info("carousel.text.draft_source: using user_text slide_count=%s", slide_count)
            return _draft_from_user_text(user_text, lang, slide_count)
        logger.info("carousel.text.draft_source: using llm topic=%r", topic)
        return self.generate_draft_slides(topic=topic, lang=lang, slide_count=slide_count)

    def compress_to_typed_slides(self, *, lang: str, slide_count: int, source_slides: list[DraftSlide]) -> list[TypedSlide]:
        logger.info("carousel.text.compaction: start slide_count=%s source=%s", slide_count, len(source_slides))
        prompt = build_compaction_prompt(
            lang=_coalesce_lang(lang),
            slide_count=slide_count,
            source_text_or_draft_slides=[slide.model_dump(mode="json") for slide in source_slides],
        )
        try:
            data = _call_json_llm(GLOBAL_TEXT_SYSTEM_PROMPT, prompt)
            items = data.get("typed_slides", [])
            normalized_items = [
                _normalize_llm_typed_item(item, index=index, slide_count=slide_count)
                for index, item in enumerate(items, start=1)
            ]
            slides = [TypedSlide.model_validate(item) for item in normalized_items]
            if len(slides) == slide_count:
                logger.info("carousel.text.compaction: llm result accepted count=%s", len(slides))
                return slides
            logger.warning("carousel.text.compaction: llm result rejected count=%s expected=%s", len(slides), slide_count)
        except Exception:
            logger.exception("carousel.text.compaction: llm compaction failed, using fallback")
        logger.info("carousel.text.compaction: using deterministic fallback")
        return _fallback_compaction(source_slides)

    def self_check_typed_slides(self, typed_slides: list[TypedSlide]) -> TypedSlidesReview:
        logger.info("carousel.text.self_check: start slides=%s", len(typed_slides))
        prompt = build_self_check_prompt(typed_slides=[slide.model_dump(mode="json") for slide in typed_slides])
        try:
            data = _call_json_llm(GLOBAL_TEXT_SYSTEM_PROMPT, prompt)
            review = TypedSlidesReview.model_validate(data)
            logger.info(
                "carousel.text.self_check: llm result accepted fixed=%s risks=%s",
                len(review.issues_fixed),
                len(review.remaining_risks),
            )
            return review
        except Exception:
            logger.exception("carousel.text.self_check: llm self-check failed, using deterministic fallback")
            return _deterministic_self_check(typed_slides)

    def build_approval_payload(self, *, lang: str, typed_slides: list[TypedSlide]) -> ApprovalPayload:
        payload = ApprovalPayload(
            lang=_coalesce_lang(lang),
            slides=[
                ApprovalSlide(
                    id=slide.id,
                    title=slide.title_block.text,
                    bullets=[block.text for block in slide.bullet_blocks],
                    emphasis_words=slide.emphasis_spans[:12],
                    cta=slide.cta,
                )
                for slide in typed_slides
            ],
            edit_rules=EditRules(),
        )
        logger.info("carousel.text.approval_payload: built slides=%s", len(payload.slides))
        return payload

    def approval_to_typed_slides(self, approval_payload: ApprovalPayload) -> list[TypedSlide]:
        logger.info("carousel.text.approval_to_typed: start slides=%s", len(approval_payload.slides))
        slides: list[TypedSlide] = []
        total = len(approval_payload.slides)
        for idx, slide in enumerate(approval_payload.slides, start=1):
            slide_type = "cover" if idx == 1 else ("cta" if idx == total else "content")
            slides.append(
                TypedSlide(
                    id=slide.id,
                    slide_type=slide_type,
                    title_block=TextBlock(text=_clean_line(slide.title, max_chars=70), max_lines=3 if idx == 1 else 2, role="title"),
                    bullet_blocks=[
                        TextBlock(text=_clean_line(item, max_chars=90), max_lines=3, role="bullet")
                        for item in slide.bullets[:6]
                    ],
                    emphasis_spans=slide.emphasis_words[:12],
                    cta=_clean_line(slide.cta, max_chars=90) if slide.cta else None,
                )
            )
        checked = self.self_check_typed_slides(slides).typed_slides_checked
        logger.info("carousel.text.approval_to_typed: completed slides=%s", len(checked))
        return checked

    def make_diverse_typed_slides(
        self,
        *,
        topic: str,
        lang: str,
        typed_slides: list[TypedSlide],
    ) -> TypedSlidesReview:
        logger.info("carousel.text.diversity: start slides=%s topic=%r", len(typed_slides), topic)
        review = self.self_check_typed_slides(typed_slides)
        diversified, diversity_fixes = _enforce_slide_diversity(
            review.typed_slides_checked,
            topic=topic,
            lang=lang,
        )
        if diversity_fixes:
            logger.warning("carousel.text.diversity: applied fixes count=%s", len(diversity_fixes))
            return TypedSlidesReview(
                typed_slides_checked=diversified,
                issues_fixed=review.issues_fixed + diversity_fixes,
                remaining_risks=review.remaining_risks,
            )
        logger.info("carousel.text.diversity: no extra fixes needed")
        return review
