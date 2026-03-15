from __future__ import annotations

import logging
import os
import random

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.schemas.carousel import (
    BBox,
    CarouselJobConfig,
    DesignTokens,
    FontPlan,
    LayerPlacement,
    LayoutTemplate,
    SlideLayerMap,
    SlideRenderResult,
    StyleVars,
    TextBlock,
    TypedSlide,
)

logger = logging.getLogger(__name__)


def _rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = ImageColor.getrgb(color)
    return r, g, b, alpha


def _relative_luminance(color: str) -> float:
    r8, g8, b8 = ImageColor.getrgb(color)

    def _channel(value: int) -> float:
        v = value / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r = _channel(r8)
    g = _channel(g8)
    b = _channel(b8)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _pick_high_contrast_color(primary: str, fallback: str, *, bg: str) -> str:
    return primary if _contrast_ratio(primary, bg) >= _contrast_ratio(fallback, bg) else fallback


def _bbox_to_box(bbox: BBox) -> tuple[int, int, int, int]:
    return bbox.x, bbox.y, bbox.x + bbox.w, bbox.y + bbox.h


def _pil_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=max(8, int(size)))


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, spacing: int, stroke_width: int) -> tuple[int, int]:
    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=spacing,
        stroke_width=stroke_width,
        align="left",
    )
    return right - left, bottom - top


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, max_width: int, stroke_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}".strip()
        left, top, right, bottom = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
        width = right - left
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class CarouselRenderService:
    @staticmethod
    def _safe_content_box(config: CarouselJobConfig) -> BBox:
        return BBox(
            x=config.safe_margins.left,
            y=config.safe_margins.top,
            w=config.canvas.w - config.safe_margins.left - config.safe_margins.right,
            h=config.canvas.h - config.safe_margins.top - config.safe_margins.bottom,
        )

    @staticmethod
    def _intersects(a: BBox, b: BBox) -> bool:
        return not (
            a.x + a.w <= b.x
            or b.x + b.w <= a.x
            or a.y + a.h <= b.y
            or b.y + b.h <= a.y
        )

    def _find_free_illustration_box(
        self,
        *,
        config: CarouselJobConfig,
        occupied: list[BBox],
        max_area_ratio: float = 0.4,
    ) -> BBox | None:
        container = self._safe_content_box(config)
        text_layers = [box for box in occupied if box.w > 0 and box.h > 0]
        preferred_top = container.y
        if text_layers:
            preferred_top = min(
                container.y + container.h - 160,
                max(box.y + box.h for box in text_layers) + 16,
            )

        xs = {container.x, container.x + container.w}
        ys = {container.y, container.y + container.h}
        for item in occupied:
            xs.add(max(container.x, item.x))
            xs.add(min(container.x + container.w, item.x + item.w))
            ys.add(max(container.y, item.y))
            ys.add(min(container.y + container.h, item.y + item.h))
        ys.add(preferred_top)
        sorted_x = sorted(xs)
        sorted_y = sorted(ys)

        best: BBox | None = None
        best_score = -1.0
        min_preferred_width = int(container.w * 0.55)
        for x1 in sorted_x:
            for x2 in sorted_x:
                if x2 <= x1:
                    continue
                for y1 in sorted_y:
                    for y2 in sorted_y:
                        if y2 <= y1:
                            continue
                        candidate = BBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1)
                        if candidate.w < 160 or candidate.h < 160:
                            continue
                        if candidate.x < container.x or candidate.y < container.y:
                            continue
                        if candidate.x + candidate.w > container.x + container.w:
                            continue
                        if candidate.y + candidate.h > container.y + container.h:
                            continue
                        if any(self._intersects(candidate, box) for box in occupied):
                            continue
                        area = candidate.w * candidate.h
                        # Prefer candidates located below text blocks and with wider span,
                        # so the asset sits under text instead of in a narrow side column.
                        below_bonus = 1.0 if candidate.y >= preferred_top else 0.0
                        width_bonus = min(1.0, candidate.w / max(1, container.w))
                        preferred_width_bonus = 0.6 if candidate.w >= min_preferred_width else 0.0
                        score = area + (below_bonus * area * 0.35) + (width_bonus * area * 0.2) + (preferred_width_bonus * area * 0.15)
                        if score > best_score:
                            best = candidate
                            best_score = score

        if best is None:
            return None

        best_area = best.w * best.h
        max_area = int(config.canvas.w * config.canvas.h * max_area_ratio)
        if best_area <= max_area:
            return best

        scale = (max_area / best_area) ** 0.5
        width = max(160, int(best.w * scale))
        height = max(160, int(best.h * scale))
        x = best.x + (best.w - width) // 2
        y = best.y + (best.h - height) // 2
        return BBox(x=x, y=y, w=width, h=height)

    def _place_background_asset(self, image: Image.Image, background_path: str) -> None:
        background = Image.open(background_path).convert("RGBA")
        background = ImageOps.fit(background, image.size, method=Image.Resampling.LANCZOS)
        image.alpha_composite(background)

    @staticmethod
    def _fit_asset_to_box(asset: Image.Image, bbox: BBox, *, fill_ratio: float = 0.96) -> Image.Image:
        asset = asset.convert("RGBA")
        asset_bbox = asset.getbbox()
        if asset_bbox:
            asset = asset.crop(asset_bbox)
        target_w = max(1, int(bbox.w * fill_ratio))
        target_h = max(1, int(bbox.h * fill_ratio))
        return ImageOps.contain(asset, (target_w, target_h))

    def _fit_single_block(
        self,
        draw: ImageDraw.ImageDraw,
        block: TextBlock,
        bbox: BBox,
        *,
        font_path: str,
        start_size: int,
        min_size: int,
        spacing: int,
        stroke_width: int,
    ) -> dict:
        max_width = max(10, bbox.w)
        for size in range(start_size, min_size - 1, -2):
            font = _pil_font(font_path, size)
            lines = _wrap_text(draw, block.text, font, max_width=max_width, stroke_width=stroke_width)
            if len(lines) > block.max_lines:
                continue
            wrapped = "\n".join(lines)
            width, height = _measure_text(draw, wrapped, font, spacing=spacing, stroke_width=stroke_width)
            if width <= bbox.w and height <= bbox.h:
                return {"font": font, "size": size, "text": wrapped, "width": width, "height": height}
        font = _pil_font(font_path, min_size)
        lines = _wrap_text(draw, block.text, font, max_width=max_width, stroke_width=stroke_width)[: block.max_lines]
        wrapped = "\n".join(lines)
        width, height = _measure_text(draw, wrapped, font, spacing=spacing, stroke_width=stroke_width)
        return {"font": font, "size": min_size, "text": wrapped, "width": min(width, bbox.w), "height": min(height, bbox.h)}

    def _fit_bullets(
        self,
        draw: ImageDraw.ImageDraw,
        blocks: list[TextBlock],
        bbox: BBox,
        *,
        font_path: str,
        start_size: int,
        min_size: int,
        spacing: int,
        stroke_width: int,
    ) -> dict:
        for size in range(start_size, min_size - 1, -2):
            font = _pil_font(font_path, size)
            wrapped_items: list[str] = []
            total_height = 0
            max_width = 0
            fits = True
            for block in blocks:
                lines = _wrap_text(draw, f"• {block.text}", font, max_width=bbox.w, stroke_width=stroke_width)
                if len(lines) > block.max_lines:
                    fits = False
                    break
                text = "\n".join(lines)
                width, height = _measure_text(draw, text, font, spacing=spacing, stroke_width=stroke_width)
                total_height += height + spacing + 16
                max_width = max(max_width, width)
                wrapped_items.append(text)
            if fits and max_width <= bbox.w and total_height <= bbox.h:
                return {"font": font, "size": size, "items": wrapped_items, "height": total_height}
        font = _pil_font(font_path, min_size)
        wrapped_items = []
        total_height = 0
        for block in blocks:
            lines = _wrap_text(draw, f"• {block.text}", font, max_width=bbox.w, stroke_width=stroke_width)[: block.max_lines]
            text = "\n".join(lines)
            _, height = _measure_text(draw, text, font, spacing=spacing, stroke_width=stroke_width)
            total_height += height + spacing + 16
            wrapped_items.append(text)
        return {"font": font, "size": min_size, "items": wrapped_items, "height": min(total_height, bbox.h)}

    def _draw_gradient_background(
        self,
        image: Image.Image,
        design_tokens: DesignTokens,
        style_vars: StyleVars,
        *,
        seed: int,
        background_visible: bool = False,
    ) -> None:
        width, height = image.size
        if background_visible:
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            top = _rgba(design_tokens.palette.bg, 72)
            bottom = _rgba(style_vars.color_bg, 108)
            for y in range(height):
                ratio = y / max(1, height - 1)
                color = tuple(int(top[i] * (1.0 - ratio) + bottom[i] * ratio) for i in range(3)) + (
                    int(top[3] * (1.0 - ratio) + bottom[3] * ratio),
                )
                draw.line((0, y, width, y), fill=color)
            image.alpha_composite(overlay)
        else:
            draw = ImageDraw.Draw(image)
            top = _rgba(design_tokens.palette.bg)
            bottom = _rgba(style_vars.color_bg)
            for y in range(height):
                ratio = y / max(1, height - 1)
                color = tuple(int(top[i] * (1.0 - ratio) + bottom[i] * ratio) for i in range(3)) + (255,)
                draw.line((0, y, width, y), fill=color)

        neon = Image.new("RGBA", image.size, (0, 0, 0, 0))
        neon_draw = ImageDraw.Draw(neon)
        rand = random.Random(seed)
        for _ in range(max(2, int(5 * style_vars.fx_lightning_density))):
            points = []
            x = rand.randint(0, width)
            y = rand.randint(0, height // 3)
            for step in range(6):
                points.append((x, y + step * rand.randint(80, 160)))
                x = max(0, min(width, x + rand.randint(-120, 120)))
            neon_draw.line(
                points,
                fill=_rgba(design_tokens.palette.accent, 200),
                width=style_vars.fx_neon_line_width,
                joint="curve",
            )
        neon = neon.filter(ImageFilter.GaussianBlur(radius=max(2, style_vars.fx_neon_blur // 4)))
        image.alpha_composite(neon)

        vignette = Image.new("L", image.size, 0)
        vignette_draw = ImageDraw.Draw(vignette)
        vignette_draw.ellipse(
            (-width * 0.15, -height * 0.1, width * 1.15, height * 1.1),
            fill=int(255 * (1.0 - style_vars.fx_vignette_intensity)),
        )
        vignette = ImageOps.invert(vignette).filter(ImageFilter.GaussianBlur(radius=140))
        vignette_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        vignette_layer.putalpha(vignette)
        image.alpha_composite(vignette_layer)

        if style_vars.fx_grain_amount > 0:
            grain = Image.new("RGBA", image.size, (0, 0, 0, 0))
            grain_draw = ImageDraw.Draw(grain)
            count = int(width * height * style_vars.fx_grain_amount / 140)
            for _ in range(count):
                x = rand.randint(0, width - 1)
                y = rand.randint(0, height - 1)
                alpha = rand.randint(6, 24)
                grain_draw.point((x, y), fill=(255, 255, 255, alpha))
            image.alpha_composite(grain)

    def _draw_card(self, image: Image.Image, bbox: BBox, *, radius: int, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int] | None = None, width: int = 0) -> None:
        card = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle(_bbox_to_box(bbox), radius=radius, fill=fill, outline=outline, width=width)
        image.alpha_composite(card)

    def _place_subject(self, image: Image.Image, subject_path: str, hero_box: BBox) -> None:
        subject = Image.open(subject_path).convert("RGBA")
        target = self._fit_asset_to_box(subject, hero_box, fill_ratio=0.98)
        x = hero_box.x + (hero_box.w - target.size[0]) // 2
        y = hero_box.y + (hero_box.h - target.size[1]) // 2
        image.alpha_composite(target, (x, y))

    def _place_illustration(self, image: Image.Image, illustration_path: str, bbox: BBox) -> None:
        illustration = Image.open(illustration_path).convert("RGBA")
        target = self._fit_asset_to_box(illustration, bbox, fill_ratio=0.97)
        x = bbox.x + (bbox.w - target.size[0]) // 2
        y = bbox.y + (bbox.h - target.size[1]) // 2
        image.alpha_composite(target, (x, y))

    def _draw_text_with_effects(
        self,
        image: Image.Image,
        *,
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: str,
        stroke_fill: str,
        stroke_width: int,
        spacing: int,
        shadow_offset: int,
        shadow_blur: int,
        shadow_color: str,
        glow_intensity: int,
        anchor: str = "la",
    ) -> None:
        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.multiline_text(
            (position[0] + shadow_offset, position[1] + shadow_offset),
            text,
            font=font,
            fill=_rgba(shadow_color, 180),
            spacing=spacing,
            stroke_width=stroke_width,
            stroke_fill=shadow_color,
            anchor=anchor,
        )
        if shadow_blur > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(1, shadow_blur // 4)))
        image.alpha_composite(shadow_layer)

        if glow_intensity > 0:
            glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            glow_draw.multiline_text(
                position,
                text,
                font=font,
                fill=_rgba(fill, 90),
                spacing=spacing,
                anchor=anchor,
            )
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(2, glow_intensity // 3)))
            image.alpha_composite(glow_layer)

        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            position,
            text,
            font=font,
            fill=fill,
            spacing=spacing,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
            anchor=anchor,
        )

    def _render_debug_boxes(
        self,
        *,
        output_path: str,
        config: CarouselJobConfig,
        layout: LayoutTemplate,
        layer_map: SlideLayerMap,
    ) -> None:
        debug = Image.new("RGB", (config.canvas.w, config.canvas.h), "#0b1020")
        draw = ImageDraw.Draw(debug)
        font = ImageFont.load_default()

        def _draw_box(bbox: BBox, label: str, color: tuple[int, int, int]) -> None:
            x1, y1, x2, y2 = _bbox_to_box(bbox)
            draw.rectangle((x1, y1, x2, y2), outline=color, width=2)
            text = f"{label} [{bbox.x},{bbox.y},{bbox.w},{bbox.h}]"
            text_w = int(draw.textlength(text, font=font))
            tag_h = 14
            tag_y = max(0, y1 - tag_h)
            draw.rectangle((x1, tag_y, min(config.canvas.w - 1, x1 + text_w + 6), tag_y + tag_h), fill=(0, 0, 0))
            draw.text((x1 + 3, tag_y + 2), text, fill=color, font=font)

        safe = self._safe_content_box(config)
        _draw_box(safe, "safe_area", (155, 155, 155))
        _draw_box(layout.title_box, "layout.title_box", (255, 212, 59))
        _draw_box(layout.bullet_box, "layout.bullet_box", (109, 213, 237))
        has_subject_layer = any(layer.name == "subject" for layer in layer_map.layers)
        if layout.hero_box and has_subject_layer:
            _draw_box(layout.hero_box, "layout.hero_box", (255, 141, 117))
        if layout.cta_box:
            _draw_box(layout.cta_box, "layout.cta_box", (115, 255, 162))
        for idx, box in enumerate(layout.illustration_boxes, start=1):
            _draw_box(box, f"layout.illustration_{idx}", (205, 149, 255))

        palette = [
            (255, 79, 79),
            (255, 180, 80),
            (80, 225, 255),
            (140, 255, 140),
            (220, 120, 255),
            (255, 255, 150),
        ]
        for idx, layer in enumerate(layer_map.layers):
            if layer.bbox is None:
                continue
            _draw_box(layer.bbox, f"layer.{layer.name}", palette[idx % len(palette)])

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        debug.save(output_path)

    def render_slide(
        self,
        *,
        output_path: str,
        debug_output_path: str | None = None,
        config: CarouselJobConfig,
        slide: TypedSlide,
        layout: LayoutTemplate,
        design_tokens: DesignTokens,
        font_plan: FontPlan,
        background_path: str | None = None,
        subject_image_path: str | None = None,
        illustration_paths: list[str] | None = None,
    ) -> SlideRenderResult:
        logger.info(
            "carousel.render.slide: start slide_id=%s template=%s background=%s subject=%s illustrations=%s",
            slide.id,
            layout.name,
            bool(background_path and os.path.exists(background_path)),
            bool(subject_image_path and os.path.exists(subject_image_path)),
            len(illustration_paths or []),
        )
        image = Image.new("RGBA", (config.canvas.w, config.canvas.h), _rgba(design_tokens.palette.bg))
        if background_path and os.path.exists(background_path):
            self._place_background_asset(image, background_path)
            self._draw_gradient_background(
                image,
                design_tokens,
                config.style_vars,
                seed=abs(hash(slide.id)) % 100000,
                background_visible=True,
            )
            layer_bg_path = background_path
        else:
            self._draw_gradient_background(image, design_tokens, config.style_vars, seed=abs(hash(slide.id)) % 100000)
            layer_bg_path = None

        layer_map = SlideLayerMap(slide_id=slide.id)
        layer_map.layers.append(LayerPlacement(name="background", path=layer_bg_path))

        if layout.hero_box and subject_image_path and os.path.exists(subject_image_path):
            self._place_subject(image, subject_image_path, layout.hero_box)
            layer_map.layers.append(LayerPlacement(name="subject", bbox=layout.hero_box, path=subject_image_path))

        title_card = BBox(
            x=max(0, layout.title_box.x - 24),
            y=max(0, layout.title_box.y - 18),
            w=min(config.canvas.w - layout.title_box.x + 24, layout.title_box.w + 48),
            h=min(config.canvas.h - layout.title_box.y + 18, layout.title_box.h + 36),
        )
        self._draw_card(
            image,
            title_card,
            radius=config.style_vars.card_radius,
            fill=_rgba("#020617", 0),
            outline=(_rgba(design_tokens.palette.accent, 70) if config.style_vars.text_card_outline_enabled else None),
            width=(config.style_vars.card_stroke if config.style_vars.text_card_outline_enabled else 0),
        )
        layer_map.layers.append(LayerPlacement(name="title_card", bbox=title_card))

        draw = ImageDraw.Draw(image)
        title_fit = self._fit_single_block(
            draw,
            slide.title_block,
            layout.title_box,
            font_path=font_plan.primary_font,
            start_size=config.style_vars.font_h1_size,
            min_size=max(28, config.style_vars.font_h1_size // 2),
            spacing=int(config.style_vars.font_h1_size * (config.style_vars.line_height_h1 - 1.0)),
            stroke_width=config.style_vars.text_stroke_width,
        )
        logger.info("carousel.render.slide: title fit slide_id=%s font_size=%s", slide.id, title_fit["size"])
        title_pos = (layout.title_box.x, layout.title_box.y)
        self._draw_text_with_effects(
            image,
            position=title_pos,
            text=title_fit["text"],
            font=title_fit["font"],
            fill=design_tokens.palette.text,
            stroke_fill=config.style_vars.text_stroke_color,
            stroke_width=config.style_vars.text_stroke_width,
            spacing=int(title_fit["size"] * (config.style_vars.line_height_h1 - 1.0)),
            shadow_offset=config.style_vars.text_shadow_xy,
            shadow_blur=config.style_vars.text_shadow_blur,
            shadow_color=config.style_vars.text_shadow_color,
            glow_intensity=config.style_vars.text_glow_intensity,
        )
        layer_map.layers.append(
            LayerPlacement(
                name="title_text",
                bbox=BBox(x=title_pos[0], y=title_pos[1], w=title_fit["width"], h=title_fit["height"]),
                meta={"font_size": title_fit["size"]},
            )
        )

        bullet_fit = self._fit_bullets(
            draw,
            slide.bullet_blocks,
            layout.bullet_box,
            font_path=font_plan.fallback_font,
            start_size=config.style_vars.font_body_size,
            min_size=max(18, config.style_vars.font_body_size // 2),
            spacing=int(config.style_vars.font_body_size * (config.style_vars.line_height_body - 1.0)),
            stroke_width=max(0, config.style_vars.text_stroke_width - 1),
        )
        logger.info(
            "carousel.render.slide: bullets fit slide_id=%s font_size=%s items=%s",
            slide.id,
            bullet_fit["size"],
            len(bullet_fit["items"]),
        )

        bullets_card_height = max(96, min(layout.bullet_box.h + 24, int(bullet_fit["height"]) + 28))
        bullets_card = BBox(
            x=max(0, layout.bullet_box.x - 12),
            y=max(0, layout.bullet_box.y - 12),
            w=min(config.canvas.w - (layout.bullet_box.x - 12), layout.bullet_box.w + 24),
            h=bullets_card_height,
        )
        self._draw_card(
            image,
            bullets_card,
            radius=config.style_vars.card_radius,
            fill=_rgba("#020617", 0),
            outline=(_rgba(design_tokens.palette.accent2, 70) if config.style_vars.text_card_outline_enabled else None),
            width=(config.style_vars.card_stroke if config.style_vars.text_card_outline_enabled else 0),
        )
        layer_map.layers.append(LayerPlacement(name="bullet_card", bbox=bullets_card))

        current_y = layout.bullet_box.y
        bullet_spacing = int(bullet_fit["size"] * 0.34)
        for idx, item in enumerate(bullet_fit["items"]):
            width, height = _measure_text(
                draw,
                item,
                bullet_fit["font"],
                spacing=int(bullet_fit["size"] * (config.style_vars.line_height_body - 1.0)),
                stroke_width=max(0, config.style_vars.text_stroke_width - 1),
            )
            self._draw_text_with_effects(
                image,
                position=(layout.bullet_box.x, current_y),
                text=item,
                font=bullet_fit["font"],
                fill=design_tokens.palette.text,
                stroke_fill=config.style_vars.text_stroke_color,
                stroke_width=max(0, config.style_vars.text_stroke_width - 1),
                spacing=int(bullet_fit["size"] * (config.style_vars.line_height_body - 1.0)),
                shadow_offset=max(1, config.style_vars.text_shadow_xy // 2),
                shadow_blur=max(1, config.style_vars.text_shadow_blur // 2),
                shadow_color=config.style_vars.text_shadow_color,
                glow_intensity=max(0, config.style_vars.text_glow_intensity // 2),
            )
            layer_map.layers.append(
                LayerPlacement(
                    name=f"bullet_{idx + 1}",
                    bbox=BBox(x=layout.bullet_box.x, y=current_y, w=width, h=height),
                    meta={"font_size": bullet_fit["size"]},
                )
            )
            current_y += height + bullet_spacing

        if slide.cta and layout.cta_box:
            self._draw_card(
                image,
                layout.cta_box,
                radius=max(18, config.style_vars.card_radius - 8),
                fill=_rgba(design_tokens.palette.cta_bar, 224),
                outline=_rgba(design_tokens.palette.accent, 120),
                width=config.style_vars.card_stroke,
            )
            cta_block = TextBlock(text=slide.cta, max_lines=2, role="cta")
            cta_fit = self._fit_single_block(
                draw,
                cta_block,
                layout.cta_box,
                font_path=font_plan.fallback_font,
                start_size=config.style_vars.font_caption_size,
                min_size=max(18, config.style_vars.font_caption_size // 2),
                spacing=8,
                stroke_width=0,
            )
            cta_x = layout.cta_box.x + 24
            cta_y = layout.cta_box.y + (layout.cta_box.h - cta_fit["height"]) // 2
            self._draw_text_with_effects(
                image,
                position=(cta_x, cta_y),
                text=cta_fit["text"],
                font=cta_fit["font"],
                fill=_pick_high_contrast_color(
                    design_tokens.palette.accent,
                    design_tokens.palette.text,
                    bg=design_tokens.palette.cta_bar,
                ),
                stroke_fill=config.style_vars.text_stroke_color,
                stroke_width=0,
                spacing=8,
                shadow_offset=0,
                shadow_blur=0,
                shadow_color=config.style_vars.text_shadow_color,
                glow_intensity=max(0, config.style_vars.text_glow_intensity // 2),
            )
            layer_map.layers.append(
                LayerPlacement(
                    name="cta",
                    bbox=BBox(x=cta_x, y=cta_y, w=cta_fit["width"], h=cta_fit["height"]),
                    meta={"font_size": cta_fit["size"]},
                )
            )
            logger.info("carousel.render.slide: cta fit slide_id=%s font_size=%s", slide.id, cta_fit["size"])

        if illustration_paths and slide.slide_type != "cta":
            illustration_path = next((path for path in illustration_paths if os.path.exists(path)), None)
            if illustration_path:
                occupied_boxes: list[BBox] = []
                for layer in layer_map.layers:
                    if layer.bbox is None:
                        continue
                    if layer.name == "subject" or layer.name == "title_text" or layer.name.startswith("bullet_") or layer.name == "cta":
                        occupied_boxes.append(layer.bbox)
                illustration_box = self._find_free_illustration_box(config=config, occupied=occupied_boxes, max_area_ratio=0.4)
                if illustration_box is not None:
                    self._place_illustration(image, illustration_path, illustration_box)
                    layer_map.layers.append(
                        LayerPlacement(name="illustration_1", bbox=illustration_box, path=illustration_path)
                    )
                    logger.info(
                        "carousel.render.slide: dynamic illustration placed slide_id=%s area=%s",
                        slide.id,
                        illustration_box.w * illustration_box.h,
                    )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
            image.convert("RGB").save(output_path, quality=config.style_vars.jpg_quality)
        else:
            image.save(output_path)
        if debug_output_path:
            self._render_debug_boxes(
                output_path=debug_output_path,
                config=config,
                layout=layout,
                layer_map=layer_map,
            )
        logger.info("carousel.render.slide: saved slide_id=%s output=%s layers=%s", slide.id, output_path, len(layer_map.layers))
        return SlideRenderResult(
            slide_id=slide.id,
            slide_path=output_path,
            layer_map=layer_map,
            template_name=layout.name,
        )
