from __future__ import annotations

import base64
import io
import logging
import os

from openai import OpenAI
from PIL import Image, ImageFilter, ImageOps, ImageDraw

from rembg import remove

from app.core.settings import settings
from app.schemas.carousel import (
    CarouselJobConfig,
    CarouselJobPaths,
    DesignTokens,
    LayoutTemplate,
    ReferenceAssets,
    StoredAsset,
    StyleVars,
    TypedSlide,
)
from app.services.layout_presets import choose_layout_template


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


def _sanitize_size(value: str, fallback: str) -> str:
    return value if value in {"1024x1024", "1024x1536", "1536x1024"} else fallback


def _open_image_from_b64(payload: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGBA")


def _trim_transparent_bounds(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image


class CarouselAssetService:
    @staticmethod
    def _images_dir(paths: CarouselJobPaths) -> str:
        directory = os.path.join(paths.assets_dir, "images")
        os.makedirs(directory, exist_ok=True)
        return directory

    def _generate_image(self, *, prompt: str, size: str) -> Image.Image | None:
        if not settings.CAROUSEL_IMAGE_GENERATION_ENABLED:
            logger.info("carousel.assets.image_gen: disabled in settings")
            return None
        try:
            logger.info("carousel.assets.image_gen: request model=%s size=%s", settings.OPENAI_IMAGE_MODEL, size)
            response = _get_client().images.generate(
                model=settings.OPENAI_IMAGE_MODEL,
                prompt=prompt,
                size=size,
            )
        except Exception:
            logger.exception("carousel.assets.image_gen: generation failed")
            return None
        data = getattr(response, "data", None) or []
        if not data:
            logger.warning("carousel.assets.image_gen: empty response data")
            return None
        b64_json = getattr(data[0], "b64_json", None)
        if not b64_json:
            logger.warning("carousel.assets.image_gen: missing b64 payload")
            return None
        try:
            logger.info("carousel.assets.image_gen: image payload received")
            return _open_image_from_b64(b64_json)
        except Exception:
            logger.exception("carousel.assets.image_gen: failed to decode image payload")
            return None

    def _build_background_prompt(
        self,
        *,
        config: CarouselJobConfig,
        design_tokens: DesignTokens,
        ref_count: int,
    ) -> str:
        return (
            "Create a portrait background for an Instagram carousel slide. "
            "No text, no letters, no numbers, no logos, no watermarks. "
            "Keep the center-left and center-right zones visually calm for future text placement. "
            f"Style: dark cinematic backdrop, neon energy lines, soft glow, gentle grain, subtle vignette. "
            f"Palette anchored on background {design_tokens.palette.bg}, accent {design_tokens.palette.accent}, "
            f"secondary accent {design_tokens.palette.accent2}. "
            f"Layout preset: {config.style_vars.layout_preset}. Reference images count: {ref_count}. "
            "The image should feel premium, editorial, contrasty and suitable for 4:5 feed."
        )

    def _build_illustration_prompt(
        self,
        *,
        slide: TypedSlide,
        design_tokens: DesignTokens,
    ) -> str:
        bullet_hint = ", ".join(block.text for block in slide.bullet_blocks[:2])
        return (
            "Create a clean editorial illustration element for a single Instagram carousel slide. "
            "No text, no letters, no numbers, no watermarks, no logos. "
            "It can be an icon card, framed scene, or abstract symbolic illustration. "
            f"Slide topic: {slide.title_block.text}. "
            f"Supporting ideas: {bullet_hint}. "
            f"Style: dark neon editorial, accent color {design_tokens.palette.accent}, "
            f"secondary accent {design_tokens.palette.accent2}, premium motion-poster aesthetic."
        )

    def _resize_cover(self, image: Image.Image, size: tuple[int, int]) -> Image.Image:
        return ImageOps.fit(image.convert("RGBA"), size, method=Image.Resampling.LANCZOS)

    def _save_generated(self, image: Image.Image, path: str) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image.save(path)
        return path

    def prepare_subject_asset(
        self,
        *,
        paths: CarouselJobPaths,
        subject_asset: StoredAsset | None,
        style_vars: StyleVars,
    ) -> str | None:
        if subject_asset is None or not os.path.exists(subject_asset.path):
            logger.info("carousel.assets.subject: no source image")
            return None

        target_path = os.path.join(self._images_dir(paths), "subject_prepared.png")
        logger.info("carousel.assets.subject: preparing source=%s target=%s", subject_asset.path, target_path)
        with open(subject_asset.path, "rb") as f:
            image_bytes = f.read()
        try:
            cutout_bytes = remove(image_bytes)
            image = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")
            logger.info("carousel.assets.subject: neural cutout applied")
        except Exception:
            logger.exception("carousel.assets.subject: cutout failed, using original image")
            image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        bbox = image.getbbox()
        if bbox:
            image = image.crop(bbox)
        image.thumbnail((620, 920))

        radius = max(8, style_vars.card_radius)
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, image.size[0], image.size[1]), radius=radius, fill=255)

        rounded = ImageOps.fit(image, image.size)
        rounded.putalpha(mask)

        shadow = Image.new("RGBA", (image.size[0] + 40, image.size[1] + 40), (0, 0, 0, 0))
        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 140))
        shadow.paste(shadow_layer, (20, 20), mask)
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, style_vars.card_shadow // 3)))
        shadow.alpha_composite(rounded, (20, 20))
        shadow.save(target_path)
        logger.info("carousel.assets.subject: prepared target=%s size=%sx%s", target_path, shadow.size[0], shadow.size[1])
        return target_path

    def generate_background_asset(
        self,
        *,
        paths: CarouselJobPaths,
        config: CarouselJobConfig,
        assets: ReferenceAssets,
        design_tokens: DesignTokens,
    ) -> str | None:
        logger.info("carousel.assets.background: generating")
        prompt = self._build_background_prompt(
            config=config,
            design_tokens=design_tokens,
            ref_count=len(assets.ref_style_images),
        )
        image = self._generate_image(
            prompt=prompt,
            size=_sanitize_size(settings.CAROUSEL_IMAGE_BACKGROUND_SIZE, "1024x1536"),
        )
        if image is None:
            logger.warning("carousel.assets.background: generation skipped or failed")
            return None
        image = self._resize_cover(image, (config.canvas.w, config.canvas.h))
        saved = self._save_generated(image, os.path.join(self._images_dir(paths), "bg.png"))
        logger.info("carousel.assets.background: saved %s", saved)
        return saved

    def generate_slide_illustrations(
        self,
        *,
        paths: CarouselJobPaths,
        config: CarouselJobConfig,
        slides: list[TypedSlide],
        design_tokens: DesignTokens,
        layout_templates: list[LayoutTemplate],
    ) -> dict[str, list[str]]:
        by_slide: dict[str, list[str]] = {}
        if not settings.CAROUSEL_IMAGE_GENERATION_ENABLED:
            logger.info("carousel.assets.illustrations: disabled in settings")
            return by_slide

        for idx, slide in enumerate(slides, start=1):
            logger.info("carousel.assets.illustrations: slide=%s index=%s", slide.id, idx)
            template = (
                choose_layout_template(
                    layout_templates,
                    slide,
                    config.style_vars,
                    has_subject_image=config.has_subject_image,
                )
                if layout_templates
                else None
            )
            if template is not None and not template.illustration_boxes:
                logger.info("carousel.assets.illustrations: skipped slide=%s no illustration boxes", slide.id)
                by_slide[slide.id] = []
                continue
            prompt = self._build_illustration_prompt(slide=slide, design_tokens=design_tokens)
            image = self._generate_image(
                prompt=prompt,
                size=_sanitize_size(settings.CAROUSEL_IMAGE_ILLUSTRATION_SIZE, "1024x1024"),
            )
            if image is None:
                logger.warning("carousel.assets.illustrations: generation failed slide=%s", slide.id)
                by_slide[slide.id] = []
                continue
            image = _trim_transparent_bounds(image)
            path = os.path.join(self._images_dir(paths), f"{slide.id}_illustration_01.png")
            self._save_generated(image, path)
            logger.info("carousel.assets.illustrations: saved slide=%s path=%s", slide.id, path)
            by_slide[slide.id] = [path]
        return by_slide

    def prepare_generated_assets(
        self,
        *,
        paths: CarouselJobPaths,
        config: CarouselJobConfig,
        assets: ReferenceAssets,
        slides: list[TypedSlide],
        design_tokens: DesignTokens,
        layout_templates: list[LayoutTemplate],
    ) -> dict[str, object]:
        logger.info("carousel.assets.pipeline: start slides=%s", len(slides))
        subject_path = self.prepare_subject_asset(
            paths=paths,
            subject_asset=assets.subject_image,
            style_vars=config.style_vars,
        )
        background_path = self.generate_background_asset(
            paths=paths,
            config=config,
            assets=assets,
            design_tokens=design_tokens,
        )
        illustrations = self.generate_slide_illustrations(
            paths=paths,
            config=config,
            slides=slides,
            design_tokens=design_tokens,
            layout_templates=layout_templates,
        )
        manifest = {
            "background_path": background_path,
            "subject_cutout_path": subject_path,
            "illustrations_by_slide": illustrations,
        }
        logger.info(
            "carousel.assets.pipeline: completed background=%s subject=%s illustration_groups=%s",
            bool(background_path),
            bool(subject_path),
            len(illustrations),
        )
        return manifest

    def collect_asset_paths(self, assets: ReferenceAssets) -> dict[str, list[str] | str | None]:
        return {
            "ref_style_images": [asset.path for asset in assets.ref_style_images if os.path.exists(asset.path)],
            "brand_assets": [asset.path for asset in assets.brand_assets if os.path.exists(asset.path)],
            "subject_image": assets.subject_image.path if assets.subject_image and os.path.exists(assets.subject_image.path) else None,
        }
