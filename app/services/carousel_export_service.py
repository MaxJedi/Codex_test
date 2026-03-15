from __future__ import annotations

import logging
import os
import zipfile

from PIL import Image, ImageOps, ImageDraw

from app.schemas.carousel import CarouselOutput, JobSpec
from app.services.storage_service import save_json

logger = logging.getLogger(__name__)


class CarouselExportService:
    def build_preview_strip(self, slide_paths: list[str], output_path: str) -> str | None:
        if not slide_paths:
            logger.info("carousel.export.preview: skipped, no slides")
            return None
        logger.info("carousel.export.preview: building slides=%s output=%s", len(slide_paths), output_path)
        thumbs: list[Image.Image] = []
        for path in slide_paths:
            image = Image.open(path).convert("RGB")
            thumbs.append(ImageOps.contain(image, (220, 275)))
        gap = 16
        width = sum(img.width for img in thumbs) + gap * (len(thumbs) - 1)
        height = max(img.height for img in thumbs) + 24
        strip = Image.new("RGB", (width, height), "#020617")
        x = 0
        for idx, img in enumerate(thumbs, start=1):
            strip.paste(img, (x, 12))
            draw = ImageDraw.Draw(strip)
            draw.text((x + 8, 8), f"{idx:02d}", fill="#E2E8F0")
            x += img.width + gap
        strip.save(output_path)
        logger.info("carousel.export.preview: saved %s", output_path)
        return output_path

    def save_job_spec(self, spec: JobSpec, output_path: str) -> str:
        save_json(output_path, spec.model_dump(mode="json"))
        logger.info("carousel.export.job_spec: saved %s", output_path)
        return output_path

    def build_zip(self, files: list[str], output_path: str, *, root_prefix: str | None = None) -> str | None:
        existing = [path for path in files if path and os.path.exists(path)]
        if not existing:
            logger.info("carousel.export.zip: skipped, no files")
            return None
        logger.info("carousel.export.zip: building files=%s output=%s", len(existing), output_path)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in existing:
                arcname = os.path.basename(path)
                if root_prefix:
                    arcname = os.path.join(root_prefix, arcname)
                archive.write(path, arcname=arcname)
        logger.info("carousel.export.zip: saved %s", output_path)
        return output_path

    def build_outputs(
        self,
        *,
        slide_paths: list[str],
        preview_strip_path: str | None,
        job_spec_path: str | None,
        zip_path: str | None,
    ) -> CarouselOutput:
        outputs = CarouselOutput(
            slide_paths=slide_paths,
            preview_strip_path=preview_strip_path,
            job_spec_path=job_spec_path,
            zip_path=zip_path,
        )
        logger.info(
            "carousel.export.outputs: built slides=%s preview=%s spec=%s zip=%s",
            len(outputs.slide_paths),
            bool(outputs.preview_strip_path),
            bool(outputs.job_spec_path),
            bool(outputs.zip_path),
        )
        return outputs
