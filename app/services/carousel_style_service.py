from __future__ import annotations

from collections import Counter
import logging

from PIL import Image

from app.schemas.carousel import (
    CarouselJobConfig,
    DesignTokens,
    FontTokens,
    LayoutTemplate,
    PaletteTokens,
    ReferenceAssets,
    EffectTokens,
    ShapeTokens,
)
from app.services.font_registry import build_font_plan, get_available_fonts
from app.services.layout_presets import build_layout_templates

logger = logging.getLogger(__name__)


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _shift(color: str, *, factor: float = 1.0, lift: int = 0) -> str:
    r, g, b = _hex_to_rgb(color)
    return _rgb_to_hex(
        (
            _clamp_channel(r * factor + lift),
            _clamp_channel(g * factor + lift),
            _clamp_channel(b * factor + lift),
        )
    )


def _extract_palette(paths: list[str]) -> list[str]:
    counter: Counter[tuple[int, int, int]] = Counter()
    for path in paths:
        try:
            image = Image.open(path).convert("RGB").resize((160, 160))
        except Exception:
            continue
        reduced = image.quantize(colors=6, method=Image.Quantize.MEDIANCUT).convert("RGB")
        counter.update(reduced.getdata())
    return [_rgb_to_hex(color) for color, _ in counter.most_common(4)]


class CarouselStyleService:
    def build_design_tokens(self, config: CarouselJobConfig, assets: ReferenceAssets) -> DesignTokens:
        logger.info("carousel.style.tokens: extracting palette refs=%s", len(assets.ref_style_images))
        palette = _extract_palette([asset.path for asset in assets.ref_style_images])

        bg = palette[0] if palette else config.style_vars.color_bg
        accent = palette[1] if len(palette) > 1 else config.style_vars.color_accent
        accent2 = palette[2] if len(palette) > 2 else config.style_vars.color_accent_2
        text = config.style_vars.color_text_main
        muted = config.style_vars.color_text_muted
        cta_bar = config.style_vars.color_cta_bar

        tokens = DesignTokens(
            palette=PaletteTokens(
                bg=bg,
                text=text,
                accent=accent,
                accent2=accent2,
                muted=muted,
                cta_bar=cta_bar,
            ),
            fonts=FontTokens(
                h1="Noto Sans" if config.lang == "ru" else "AUTO",
                body="DejaVu Sans" if config.lang == "ru" else "AUTO",
            ),
            effects=EffectTokens(
                glow=config.style_vars.text_glow_intensity,
                grain=config.style_vars.fx_grain_amount,
                vignette=config.style_vars.fx_vignette_intensity,
                lightning=config.style_vars.fx_lightning_density,
            ),
            shape=ShapeTokens(
                radius=config.style_vars.card_radius,
                stroke=config.style_vars.card_stroke,
            ),
        )
        logger.info(
            "carousel.style.tokens: built bg=%s accent=%s accent2=%s",
            tokens.palette.bg,
            tokens.palette.accent,
            tokens.palette.accent2,
        )
        return tokens

    def build_layout_templates(self, config: CarouselJobConfig) -> list[LayoutTemplate]:
        layouts = build_layout_templates(config.canvas, config.safe_margins, config.style_vars)
        logger.info("carousel.style.layouts: built count=%s preset=%s", len(layouts), config.style_vars.layout_preset)
        return layouts

    def build_font_plan(self, config: CarouselJobConfig, design_tokens: DesignTokens):
        plan = build_font_plan(config.lang, design_tokens, get_available_fonts())
        logger.info("carousel.style.fonts: primary=%s fallback=%s", plan.primary_font, plan.fallback_font)
        return plan

    def build_style_bundle(self, config: CarouselJobConfig, assets: ReferenceAssets):
        logger.info("carousel.style.bundle: start")
        design_tokens = self.build_design_tokens(config, assets)
        bundle = {
            "design_tokens": design_tokens,
            "layout_templates": self.build_layout_templates(config),
            "font_plan": self.build_font_plan(config, design_tokens),
        }
        logger.info("carousel.style.bundle: completed")
        return bundle
