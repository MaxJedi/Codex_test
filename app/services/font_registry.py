from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

from app.core.settings import settings
from app.schemas.carousel import CarouselFontOption, DesignTokens, FontPlan

FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2"}
AUTO_FONT_NAME = "AUTO"


def get_carousel_fonts_dir() -> str:
    configured = settings.CAROUSEL_FONTS_DIR.strip()
    if os.path.isabs(configured):
        return configured
    project_root = Path(__file__).resolve().parents[2]
    return str(project_root / configured)


def _existing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if path and os.path.exists(path)]


def _font_display_name(path: str) -> str:
    stem = Path(path).stem
    cleaned = re.sub(
        r"[-_\s]+(regular|bold|italic|medium|light|thin|black|vf)(\b.*)?$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*", " ", cleaned)
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or stem


def _font_sort_key(path: str) -> tuple[int, str]:
    base = os.path.basename(path).lower()
    priority = 0
    if "regular" in base or "book" in base:
        priority = 0
    elif "medium" in base:
        priority = 1
    elif "bold" in base:
        priority = 2
    else:
        priority = 3
    return priority, base


def _scan_font_directory(directory: str) -> dict[str, str]:
    registry: dict[str, str] = {}
    if not os.path.isdir(directory):
        return registry

    candidates: list[str] = []
    for entry in sorted(os.listdir(directory)):
        path = os.path.join(directory, entry)
        if not os.path.isfile(path):
            continue
        if Path(path).suffix.lower() not in FONT_EXTENSIONS:
            continue
        candidates.append(path)

    candidates.sort(key=_font_sort_key)
    used_names: dict[str, int] = {}
    for path in candidates:
        name = _font_display_name(path)
        count = used_names.get(name, 0)
        used_names[name] = count + 1
        key = name if count == 0 else f"{name} ({count + 1})"
        registry.setdefault(key, path)
    return registry


def _scan_system_fonts() -> dict[str, str]:
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
        elif "dejavu" in base:
            registry.setdefault("DejaVu Sans", path)
    return registry


def get_available_fonts() -> dict[str, str]:
    registry: dict[str, str] = {}
    registry.update(_scan_system_fonts())
    project_fonts = _scan_font_directory(get_carousel_fonts_dir())
    registry.update(project_fonts)

    auto_candidates = list(project_fonts.values()) or list(_scan_system_fonts().values())
    if auto_candidates:
        registry[AUTO_FONT_NAME] = auto_candidates[0]
    elif os.path.exists(settings.DRAW_TEXT_FONT_PATH):
        registry[AUTO_FONT_NAME] = settings.DRAW_TEXT_FONT_PATH
    return registry


def list_carousel_font_options() -> list[CarouselFontOption]:
    options: list[CarouselFontOption] = []
    for name, path in get_available_fonts().items():
        if name == AUTO_FONT_NAME:
            continue
        filename = os.path.basename(path)
        options.append(
            CarouselFontOption(
                id=filename,
                name=name,
                filename=filename,
                url=f"/content/carousel/fonts/{quote(filename)}",
            )
        )
    options.sort(key=lambda item: item.name.lower())
    return options


def resolve_carousel_font_file(filename: str) -> str | None:
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        return None

    fonts_dir = get_carousel_fonts_dir()
    candidate = os.path.join(fonts_dir, safe_name)
    if not os.path.isfile(candidate):
        return None
    if Path(candidate).suffix.lower() not in FONT_EXTENSIONS:
        return None
    return candidate


def _resolve_font_path(name: str, available: dict[str, str]) -> str | None:
    if name and name != AUTO_FONT_NAME and name in available:
        return available[name]
    return available.get(AUTO_FONT_NAME)


def build_font_plan(lang: str, design_tokens: DesignTokens, available_fonts: dict[str, str] | None = None) -> FontPlan:
    available = available_fonts or get_available_fonts()

    primary_font = _resolve_font_path(design_tokens.fonts.h1, available)
    subtitle_font = _resolve_font_path(design_tokens.fonts.subtitle, available)
    fallback_font = _resolve_font_path(design_tokens.fonts.body, available)

    if not primary_font:
        primary_font = settings.DRAW_TEXT_FONT_PATH if os.path.exists(settings.DRAW_TEXT_FONT_PATH) else None
    if not fallback_font:
        fallback_font = primary_font
    if not subtitle_font:
        subtitle_font = fallback_font or primary_font

    if not primary_font:
        primary_font = subtitle_font or fallback_font or settings.DRAW_TEXT_FONT_PATH
    if not fallback_font:
        fallback_font = primary_font
    if not subtitle_font:
        subtitle_font = fallback_font

    font_paths = [primary_font, subtitle_font, fallback_font]
    supports_cyr = lang in ("ru", "auto") and any(os.path.exists(path) for path in font_paths)
    return FontPlan(
        primary_font=primary_font,
        subtitle_font=subtitle_font,
        fallback_font=fallback_font,
        weights={"h1": 700, "subtitle": 600, "body": 500},
        supports={
            "cyrillic": supports_cyr,
            "latin": True,
        },
    )
