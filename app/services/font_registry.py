from __future__ import annotations

import os

from app.core.settings import settings
from app.schemas.carousel import DesignTokens, FontPlan


def _existing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if path and os.path.exists(path)]


def get_available_fonts() -> dict[str, str]:
    fallback_candidates = [
        item.strip()
        for item in settings.CAROUSEL_FONT_FALLBACK_PATHS.split(",")
        if item.strip()
    ]
    known_paths = _existing_paths(
        [
            settings.DRAW_TEXT_FONT_PATH,
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            *fallback_candidates,
        ]
    )

    registry: dict[str, str] = {}
    for path in known_paths:
        base = os.path.basename(path).lower()
        if "noto" in base:
            registry.setdefault("Noto Sans", path)
        if "dejavu" in base:
            registry.setdefault("DejaVu Sans", path)
    if known_paths:
        registry.setdefault("AUTO", known_paths[0])
    return registry


def build_font_plan(lang: str, design_tokens: DesignTokens, available_fonts: dict[str, str] | None = None) -> FontPlan:
    available = available_fonts or get_available_fonts()
    primary_name = design_tokens.fonts.h1 if design_tokens.fonts.h1 in available else "AUTO"
    body_name = design_tokens.fonts.body if design_tokens.fonts.body in available else "AUTO"

    primary_font = available.get(primary_name) or available.get("Noto Sans") or available.get("DejaVu Sans")
    fallback_font = available.get(body_name) or available.get("Noto Sans") or available.get("DejaVu Sans") or primary_font
    if not primary_font:
        primary_font = settings.DRAW_TEXT_FONT_PATH
    if not fallback_font:
        fallback_font = primary_font

    supports_cyr = any("noto" in os.path.basename(path).lower() or "dejavu" in os.path.basename(path).lower() for path in (primary_font, fallback_font))
    supports_lat = True
    return FontPlan(
        primary_font=primary_font,
        fallback_font=fallback_font,
        weights={"h1": 700, "body": 500},
        supports={
            "cyrillic": supports_cyr if lang in ("ru", "auto") else False,
            "latin": supports_lat,
        },
    )
