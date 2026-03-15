from __future__ import annotations

from app.schemas.carousel import BBox, CanvasSize, LayoutTemplate, SafeMargins, StyleVars, TypedSlide


def _content_width(canvas: CanvasSize, safe: SafeMargins) -> int:
    return canvas.w - safe.left - safe.right


def build_layout_templates(canvas: CanvasSize, safe: SafeMargins, style_vars: StyleVars) -> list[LayoutTemplate]:
    content_w = _content_width(canvas, safe)
    hero_w = int(content_w * 0.38)
    text_w = content_w - hero_w - 24
    full_h = canvas.h - safe.top - safe.bottom
    cta_h = 110 if style_vars.cta_enabled else 0
    main_h = full_h - cta_h - 24

    hero_left = LayoutTemplate(
        name="hero_left",
        title_box=BBox(x=safe.left + hero_w + 24, y=safe.top + 28, w=text_w, h=300),
        bullet_box=BBox(x=safe.left + hero_w + 24, y=safe.top + 356, w=text_w, h=main_h - 356),
        hero_box=BBox(x=safe.left, y=safe.top + 20, w=hero_w, h=min(main_h, 800)),
        cta_box=BBox(x=safe.left, y=canvas.h - safe.bottom - 92, w=content_w, h=92) if style_vars.cta_enabled else None,
        illustration_boxes=[BBox(x=safe.left + hero_w + 24, y=safe.top + 740, w=text_w, h=300)],
        clean_zones=[BBox(x=safe.left + hero_w + 24, y=safe.top + 28, w=text_w, h=main_h)],
    )

    hero_right = LayoutTemplate(
        name="hero_right",
        title_box=BBox(x=safe.left, y=safe.top + 28, w=text_w, h=300),
        bullet_box=BBox(x=safe.left, y=safe.top + 356, w=text_w, h=main_h - 356),
        hero_box=BBox(x=safe.left + text_w + 24, y=safe.top + 20, w=hero_w, h=min(main_h, 800)),
        cta_box=BBox(x=safe.left, y=canvas.h - safe.bottom - 92, w=content_w, h=92) if style_vars.cta_enabled else None,
        illustration_boxes=[BBox(x=safe.left, y=safe.top + 740, w=text_w, h=300)],
        clean_zones=[BBox(x=safe.left, y=safe.top + 28, w=text_w, h=main_h)],
    )

    text_only = LayoutTemplate(
        name="text_only",
        title_box=BBox(x=safe.left, y=safe.top + 48, w=content_w, h=280),
        bullet_box=BBox(x=safe.left, y=safe.top + 356, w=content_w, h=420),
        cta_box=BBox(x=safe.left, y=canvas.h - safe.bottom - 92, w=content_w, h=92) if style_vars.cta_enabled else None,
        illustration_boxes=[BBox(x=safe.left, y=safe.top + 820, w=content_w, h=300)],
        clean_zones=[BBox(x=safe.left, y=safe.top, w=content_w, h=full_h)],
    )

    cards_grid = LayoutTemplate(
        name="cards_grid",
        title_box=BBox(x=safe.left, y=safe.top + 36, w=content_w, h=250),
        bullet_box=BBox(x=safe.left, y=safe.top + 312, w=content_w, h=full_h - 380),
        cta_box=BBox(x=safe.left, y=canvas.h - safe.bottom - 92, w=content_w, h=92) if style_vars.cta_enabled else None,
        illustration_boxes=[
            BBox(x=safe.left, y=safe.top + 760, w=(content_w - 16) // 2, h=210),
            BBox(x=safe.left + (content_w + 16) // 2, y=safe.top + 760, w=(content_w - 16) // 2, h=210),
        ],
        clean_zones=[BBox(x=safe.left, y=safe.top + 36, w=content_w, h=full_h)],
    )
    return [hero_left, hero_right, text_only, cards_grid]


def choose_layout_template(
    templates: list[LayoutTemplate],
    slide: TypedSlide,
    style_vars: StyleVars,
    *,
    has_subject_image: bool = False,
) -> LayoutTemplate:
    by_name = {template.name: template for template in templates}
    if slide.slide_type == "cover":
        if style_vars.hero_enabled and has_subject_image:
            return by_name.get("hero_right", templates[0])
        return by_name.get("text_only", templates[0])
    if slide.slide_type == "cta":
        return by_name.get("text_only", templates[0])
    if style_vars.hero_enabled and has_subject_image:
        return by_name.get("hero_left" if style_vars.hero_side == "left" else "hero_right", templates[0])
    return by_name.get(style_vars.layout_preset, templates[0])
