from __future__ import annotations

import logging

from app.schemas.carousel import (
    BBox,
    CarouselJobConfig,
    QaIssue,
    QaReport,
    SlideQaReport,
    SlideRenderResult,
    TypedSlide,
)

logger = logging.getLogger(__name__)


def _intersects(a: BBox, b: BBox) -> bool:
    return not (
        a.x + a.w <= b.x
        or b.x + b.w <= a.x
        or a.y + a.h <= b.y
        or b.y + b.h <= a.y
    )


class CarouselQaService:
    @staticmethod
    def _is_bullet_text_layer(name: str) -> bool:
        if not name.startswith("bullet_"):
            return False
        suffix = name.removeprefix("bullet_")
        return suffix.isdigit()

    @staticmethod
    def _layout_layers(render_result: SlideRenderResult) -> list:
        return [
            layer
            for layer in render_result.layer_map.layers
            if layer.bbox and (
                layer.name == "title_text"
                or CarouselQaService._is_bullet_text_layer(layer.name)
                or layer.name == "cta"
            )
        ]

    def validate_slide(
        self,
        *,
        render_result: SlideRenderResult,
        slide: TypedSlide,
        config: CarouselJobConfig,
    ) -> SlideQaReport:
        logger.info("carousel.qa.slide: validating slide_id=%s", slide.id)
        issues: list[QaIssue] = []
        text_layers = self._layout_layers(render_result)
        safe = config.safe_margins

        for layer in text_layers:
            bbox = layer.bbox
            if bbox is None:
                continue
            if bbox.x < safe.left or bbox.y < safe.top:
                issues.append(QaIssue(kind="safe_margin", message=f"{layer.name}: выходит за верхние/левые safe margins", severity="error"))
            if bbox.x + bbox.w > config.canvas.w - safe.right or bbox.y + bbox.h > config.canvas.h - safe.bottom:
                issues.append(QaIssue(kind="safe_margin", message=f"{layer.name}: выходит за нижние/правые safe margins", severity="error"))

        for idx, layer in enumerate(text_layers):
            if layer.bbox is None:
                continue
            for other in text_layers[idx + 1:]:
                if other.bbox is None:
                    continue
                if _intersects(layer.bbox, other.bbox):
                    issues.append(QaIssue(kind="overlap", message=f"{layer.name} пересекается с {other.name}", severity="error"))

        for layer in text_layers:
            font_size = layer.meta.get("font_size") if isinstance(layer.meta, dict) else None
            if not isinstance(font_size, int):
                continue
            if layer.name == "title_text":
                if font_size < 28:
                    issues.append(QaIssue(kind="readability", message=f"{layer.name}: слишком мелкий шрифт ({font_size}px)", severity="warning"))
            elif self._is_bullet_text_layer(layer.name):
                if font_size < 22:
                    issues.append(QaIssue(kind="readability", message=f"{layer.name}: слишком мелкий шрифт ({font_size}px)", severity="warning"))
            elif layer.name == "cta":
                if font_size < 20:
                    issues.append(QaIssue(kind="readability", message=f"{layer.name}: слишком мелкий шрифт ({font_size}px)", severity="warning"))

        bullet_layers = [layer for layer in text_layers if self._is_bullet_text_layer(layer.name)]
        if len(bullet_layers) >= 5:
            bullet_sizes = [
                layer.meta.get("font_size")
                for layer in bullet_layers
                if isinstance(layer.meta, dict) and isinstance(layer.meta.get("font_size"), int)
            ]
            if bullet_sizes and min(bullet_sizes) < 26:
                issues.append(
                    QaIssue(
                        kind="readability",
                        message="Слишком высокая плотность буллетов: уменьшите число пунктов или увеличьте размер текста",
                        severity="warning",
                    )
                )

        if not slide.bullet_blocks and slide.slide_type == "content":
            issues.append(QaIssue(kind="content_density", message="Контентный слайд без буллетов", severity="warning"))

        report = SlideQaReport(
            slide_id=slide.id,
            ok=not any(item.severity == "error" for item in issues),
            issues=issues,
            fixes_applied=[],
            final_slide_path=render_result.slide_path,
        )
        logger.info("carousel.qa.slide: done slide_id=%s ok=%s issues=%s", slide.id, report.ok, len(report.issues))
        return report

    def validate_carousel(
        self,
        *,
        render_results: list[SlideRenderResult],
        slides: list[TypedSlide],
        config: CarouselJobConfig,
    ) -> QaReport:
        logger.info("carousel.qa.carousel: validating slides=%s", len(render_results))
        reports = [
            self.validate_slide(render_result=result, slide=slide, config=config)
            for result, slide in zip(render_results, slides, strict=False)
        ]
        report = QaReport(
            overall_ok=all(item.ok for item in reports),
            slides=reports,
        )
        logger.info(
            "carousel.qa.carousel: done overall_ok=%s total_issues=%s",
            report.overall_ok,
            sum(len(item.issues) for item in report.slides),
        )
        return report
