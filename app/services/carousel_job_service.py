from __future__ import annotations

import logging
import os
import uuid

from pydantic import TypeAdapter

from app.schemas.carousel import (
    ApprovalPayload,
    ApprovalSubmitRequest,
    CarouselApproveResponse,
    CarouselCreateRequest,
    CarouselDraftResponse,
    CarouselJobConfig,
    CarouselJobDetailResponse,
    CarouselJobResponse,
    CarouselOutput,
    CarouselRenderResponse,
    JobSpec,
    QaReport,
    ReferenceAssets,
    TypedSlide,
)
from app.services.carousel_asset_service import CarouselAssetService
from app.services.carousel_export_service import CarouselExportService
from app.services.carousel_qa_service import CarouselQaService
from app.services.carousel_render_service import CarouselRenderService
from app.services.carousel_style_service import CarouselStyleService
from app.services.carousel_text_service import CarouselTextService
from app.services.layout_presets import choose_layout_template
from app.services.storage_service import (
    build_job_manifest,
    create_carousel_job_dir,
    load_job_status,
    read_json_if_exists,
    save_job_model,
    save_job_status,
)

logger = logging.getLogger(__name__)


class CarouselJobService:
    def __init__(self) -> None:
        self.text_service = CarouselTextService()
        self.style_service = CarouselStyleService()
        self.asset_service = CarouselAssetService()
        self.render_service = CarouselRenderService()
        self.qa_service = CarouselQaService()
        self.export_service = CarouselExportService()

    def _load_required_state(self, job_id: str):
        state = load_job_status(job_id)
        if state is None:
            logger.warning("carousel.job.load_state: missing job_id=%s", job_id)
            raise FileNotFoundError(f"Unknown carousel job: {job_id}")
        return state

    def _load_required_model(self, path: str, model_cls):
        raw = read_json_if_exists(path)
        if raw is None:
            raise FileNotFoundError(path)
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(raw)
        return TypeAdapter(model_cls).validate_python(raw)

    def _load_optional_model(self, path: str, model_cls):
        raw = read_json_if_exists(path)
        if raw is None:
            return None
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(raw)
        return TypeAdapter(model_cls).validate_python(raw)

    def create_job(self, payload: CarouselCreateRequest, assets: ReferenceAssets, *, job_id: str | None = None) -> CarouselJobResponse:
        job_id = job_id or f"carousel_{uuid.uuid4().hex[:12]}"
        logger.info(
            "carousel.job.create: job_id=%s topic=%r lang=%s slide_count=%s refs=%s subject=%s",
            job_id,
            payload.topic,
            payload.lang,
            payload.slide_count,
            len(assets.ref_style_images),
            bool(assets.subject_image),
        )
        paths = create_carousel_job_dir(job_id)
        config = self.text_service.build_job_config(
            payload,
            ref_count=len(assets.ref_style_images),
            has_subject_image=assets.subject_image is not None,
        )
        state = build_job_manifest(job_id, paths)
        save_job_model(paths, "job_config.json", config)
        save_job_model(paths, "input_request.json", payload, bucket="inputs")
        save_job_model(paths, "assets.json", assets, bucket="inputs")
        save_job_status(state)
        logger.info("carousel.job.create: persisted job_id=%s root=%s", job_id, paths.root)
        return CarouselJobResponse(job_id=job_id, status=state.status, config=config, assets=assets)

    def generate_draft(self, job_id: str) -> CarouselDraftResponse:
        state = self._load_required_state(job_id)
        logger.info("carousel.job.draft: loading inputs job_id=%s", job_id)
        payload = self._load_required_model(os.path.join(state.paths.inputs_dir, "input_request.json"), CarouselCreateRequest)
        config = self._load_required_model(os.path.join(state.paths.intermediate_dir, "job_config.json"), CarouselJobConfig)
        try:
            logger.info("carousel.job.draft: building source draft slides job_id=%s", job_id)
            draft_slides = self.text_service.build_source_draft_slides(
                topic=payload.topic,
                lang=config.lang,
                slide_count=config.slide_count,
                user_text=payload.user_text,
            )
            logger.info("carousel.job.draft: draft slides ready job_id=%s count=%s", job_id, len(draft_slides))
            typed_slides = self.text_service.compress_to_typed_slides(
                lang=config.lang,
                slide_count=config.slide_count,
                source_slides=draft_slides,
            )
            logger.info("carousel.job.draft: typed slides ready job_id=%s count=%s", job_id, len(typed_slides))
            save_job_model(state.paths, "typed_slides_for_llm_review.json", typed_slides)
            review = self.text_service.make_diverse_typed_slides(
                topic=payload.topic,
                lang=config.lang,
                typed_slides=typed_slides,
            )
            logger.info(
                "carousel.job.draft: review complete job_id=%s fixed=%s risks=%s",
                job_id,
                len(review.issues_fixed),
                len(review.remaining_risks),
            )
            approval_payload = self.text_service.build_approval_payload(
                lang=config.lang,
                typed_slides=review.typed_slides_checked,
            )
            logger.info("carousel.job.draft: approval payload ready job_id=%s slides=%s", job_id, len(approval_payload.slides))

            save_job_model(state.paths, "draft_slides.json", draft_slides)
            save_job_model(state.paths, "typed_slides.json", typed_slides)
            save_job_model(state.paths, "typed_slides_review_result.json", review)
            save_job_model(state.paths, "typed_slides_checked.json", review)
            save_job_model(state.paths, "text_slides_final.json", review.typed_slides_checked)
            save_job_model(state.paths, "approval_payload.json", approval_payload)

            state.status = "draft_ready"
            state.current_step = "approval_required"
            save_job_status(state)
            logger.info("carousel.job.draft: completed job_id=%s status=%s", job_id, state.status)
            return CarouselDraftResponse(job_id=job_id, status=state.status, approval_payload=approval_payload)
        except Exception as exc:
            state.status = "failed"
            state.current_step = "draft_failed"
            state.error = str(exc)
            save_job_status(state)
            logger.exception("carousel.job.draft: failed job_id=%s", job_id)
            raise

    def approve(self, job_id: str, request: ApprovalSubmitRequest) -> CarouselApproveResponse:
        state = self._load_required_state(job_id)
        logger.info("carousel.job.approve: start job_id=%s slides=%s", job_id, len(request.slides))
        base_payload = self._load_required_model(os.path.join(state.paths.intermediate_dir, "approval_payload.json"), ApprovalPayload)
        merged_payload = base_payload.model_copy(update={"slides": request.slides})
        typed_slides = self.text_service.approval_to_typed_slides(merged_payload)

        save_job_model(state.paths, "approval_payload.json", merged_payload)
        save_job_model(state.paths, "approval_submit_slides.json", request.slides)
        save_job_model(state.paths, "approved_slides.json", typed_slides)

        state.status = "approved"
        state.current_step = "approved"
        save_job_status(state)
        logger.info("carousel.job.approve: completed job_id=%s approved_slides=%s", job_id, len(typed_slides))
        return CarouselApproveResponse(job_id=job_id, status=state.status, typed_slides=typed_slides)

    def _render_once(
        self,
        *,
        config: CarouselJobConfig,
        assets: ReferenceAssets,
        slides: list[TypedSlide],
        state,
        style_bundle: dict | None = None,
        asset_manifest: dict | None = None,
    ) -> tuple[list, QaReport, dict, dict]:
        if style_bundle is None:
            logger.info("carousel.job.render_once: style bundle job_id=%s", state.job_id)
            style_bundle = self.style_service.build_style_bundle(config, assets)
        else:
            logger.info("carousel.job.render_once: reusing style bundle job_id=%s", state.job_id)
        design_tokens = style_bundle["design_tokens"]
        layout_templates = style_bundle["layout_templates"]
        font_plan = style_bundle["font_plan"]
        logger.info(
            "carousel.job.render_once: style ready job_id=%s layouts=%s primary_font=%s",
            state.job_id,
            len(layout_templates),
            font_plan.primary_font,
        )
        if asset_manifest is None:
            asset_manifest = self.asset_service.prepare_generated_assets(
                paths=state.paths,
                config=config,
                assets=assets,
                slides=slides,
                design_tokens=design_tokens,
                layout_templates=layout_templates,
            )
        else:
            logger.info("carousel.job.render_once: reusing generated assets job_id=%s", state.job_id)
        logger.info(
            "carousel.job.render_once: assets ready job_id=%s background=%s subject=%s illustrated_slides=%s",
            state.job_id,
            bool(asset_manifest.get("background_path")),
            bool(asset_manifest.get("subject_cutout_path")),
            sum(1 for items in (asset_manifest.get("illustrations_by_slide") or {}).values() if items),
        )

        ext = config.output_format
        render_results = []
        debug_paths_rel: list[str] = []
        total_slides = len(slides)
        for idx, slide in enumerate(slides, start=1):
            layout = choose_layout_template(
                layout_templates,
                slide,
                config.style_vars,
                has_subject_image=config.has_subject_image,
            )
            output_path = os.path.join(state.paths.slides_dir, f"{idx:02d}.{ext}")
            debug_output_path = os.path.join(state.paths.debug_slides_dir, f"{idx:02d}_boxes.png")
            logger.info(
                "carousel.job.render_once: rendering slide job_id=%s slide_id=%s output=%s layout=%s",
                state.job_id,
                slide.id,
                output_path,
                layout.name,
            )
            render_results.append(
                self.render_service.render_slide(
                    output_path=output_path,
                    debug_output_path=debug_output_path,
                    config=config,
                    slide=slide,
                    layout=layout,
                    design_tokens=design_tokens,
                    font_plan=font_plan,
                    background_path=asset_manifest.get("background_path"),
                    subject_image_path=asset_manifest.get("subject_cutout_path") if idx == 1 else None,
                    illustration_paths=(
                        []
                        if idx == total_slides and not config.style_vars.allow_illustration_on_last_slide
                        else (asset_manifest.get("illustrations_by_slide") or {}).get(slide.id, [])
                    ),
                )
            )
            debug_paths_rel.append(os.path.relpath(debug_output_path, state.paths.root))

        logger.info("carousel.job.render_once: qa validation job_id=%s slides=%s", state.job_id, len(render_results))
        qa_report = self.qa_service.validate_carousel(
            render_results=render_results,
            slides=slides,
            config=config,
        )
        logger.info(
            "carousel.job.render_once: qa complete job_id=%s overall_ok=%s issue_count=%s",
            state.job_id,
            qa_report.overall_ok,
            sum(len(item.issues) for item in qa_report.slides),
        )
        save_job_model(state.paths, "debug_slide_boxes.json", {"paths": debug_paths_rel})
        return render_results, qa_report, style_bundle, asset_manifest

    def render(self, job_id: str) -> CarouselRenderResponse:
        state = self._load_required_state(job_id)
        logger.info("carousel.job.render: loading state job_id=%s", job_id)
        config = self._load_required_model(os.path.join(state.paths.intermediate_dir, "job_config.json"), CarouselJobConfig)
        assets = self._load_required_model(os.path.join(state.paths.inputs_dir, "assets.json"), ReferenceAssets)
        slides = self._load_required_model(os.path.join(state.paths.intermediate_dir, "approved_slides.json"), list[TypedSlide])

        state.status = "rendering"
        state.current_step = "rendering"
        state.error = None
        save_job_status(state)

        try:
            logger.info("carousel.job.render: first pass job_id=%s slides=%s", job_id, len(slides))
            render_results, qa_report, style_bundle, asset_manifest = self._render_once(
                config=config,
                assets=assets,
                slides=slides,
                state=state,
            )
            save_job_model(state.paths, "asset_manifest.json", asset_manifest)
            save_job_model(state.paths, "qa_report_first_pass.json", qa_report)
            if not qa_report.overall_ok:
                logger.warning("carousel.job.render: qa failed first pass job_id=%s retrying with smaller fonts", job_id)
                smaller_style = config.style_vars.model_copy(
                    update={
                        "font_h1_size": max(40, int(config.style_vars.font_h1_size * 0.9)),
                        "font_body_size": max(24, int(config.style_vars.font_body_size * 0.92)),
                        "font_caption_size": max(20, int(config.style_vars.font_caption_size * 0.92)),
                    }
                )
                retry_config = config.model_copy(update={"style_vars": smaller_style})
                retry_results, retry_report, retry_bundle, retry_assets = self._render_once(
                    config=retry_config,
                    assets=assets,
                    slides=slides,
                    state=state,
                    style_bundle=style_bundle,
                    asset_manifest=asset_manifest,
                )
                save_job_model(state.paths, "qa_report_retry.json", retry_report)
                if retry_report.overall_ok or sum(len(item.issues) for item in retry_report.slides) <= sum(len(item.issues) for item in qa_report.slides):
                    logger.info("carousel.job.render: retry accepted job_id=%s overall_ok=%s", job_id, retry_report.overall_ok)
                    render_results = retry_results
                    qa_report = retry_report
                    style_bundle = retry_bundle
                    asset_manifest = retry_assets
                    config = retry_config
                    for report in qa_report.slides:
                        report.fixes_applied.append("Reduced font sizes for safe fit")
                    save_job_model(state.paths, "job_config.json", config)
                else:
                    logger.info("carousel.job.render: keeping first pass after retry comparison job_id=%s", job_id)

            slide_paths_abs = [item.slide_path for item in render_results]
            slide_paths_rel = [os.path.relpath(path, state.paths.root) for path in slide_paths_abs]
            preview_abs = os.path.join(state.paths.exports_dir, "preview_strip.png")
            job_spec_abs = os.path.join(state.paths.exports_dir, "job_spec.json")
            zip_abs = os.path.join(state.paths.exports_dir, f"carousel_{job_id}.zip")

            preview_rel = None
            built_preview = self.export_service.build_preview_strip(slide_paths_abs, preview_abs)
            if built_preview:
                preview_rel = os.path.relpath(built_preview, state.paths.root)
            logger.info("carousel.job.render: preview ready job_id=%s has_preview=%s", job_id, bool(preview_rel))

            spec = JobSpec(
                job_id=job_id,
                config=config,
                approved_slides=slides,
                design_tokens=style_bundle["design_tokens"],
                layout_templates=style_bundle["layout_templates"],
                font_plan=style_bundle["font_plan"],
                asset_manifest=asset_manifest,
                outputs=slide_paths_rel,
                qa_report=qa_report,
            )
            job_spec_rel = os.path.relpath(self.export_service.save_job_spec(spec, job_spec_abs), state.paths.root)
            zip_rel = None
            built_zip = self.export_service.build_zip(
                slide_paths_abs + ([preview_abs] if preview_rel else []) + [job_spec_abs],
                zip_abs,
                root_prefix=job_id,
            )
            if built_zip:
                zip_rel = os.path.relpath(built_zip, state.paths.root)
            logger.info("carousel.job.render: export bundle ready job_id=%s has_zip=%s", job_id, bool(zip_rel))

            outputs = self.export_service.build_outputs(
                slide_paths=slide_paths_rel,
                preview_strip_path=preview_rel,
                job_spec_path=job_spec_rel,
                zip_path=zip_rel,
            )

            save_job_model(state.paths, "design_tokens.json", style_bundle["design_tokens"])
            save_job_model(state.paths, "layout_templates.json", style_bundle["layout_templates"])
            save_job_model(state.paths, "font_plan.json", style_bundle["font_plan"])
            save_job_model(state.paths, "asset_manifest.json", asset_manifest)
            save_job_model(state.paths, "qa_report.json", qa_report)
            save_job_model(state.paths, "outputs.json", outputs, bucket="exports")

            state.status = "completed"
            state.current_step = "completed"
            save_job_status(state)
            logger.info("carousel.job.render: completed job_id=%s", job_id)
            return CarouselRenderResponse(job_id=job_id, status=state.status, outputs=outputs, qa_report=qa_report)
        except Exception as exc:
            state.status = "failed"
            state.current_step = "render_failed"
            state.error = str(exc)
            save_job_status(state)
            logger.exception("carousel.job.render: failed job_id=%s", job_id)
            raise

    def get_job_detail(self, job_id: str) -> CarouselJobDetailResponse:
        state = self._load_required_state(job_id)
        logger.info("carousel.job.detail: loading job_id=%s", job_id)
        config = self._load_optional_model(os.path.join(state.paths.intermediate_dir, "job_config.json"), CarouselJobConfig)
        assets = self._load_optional_model(os.path.join(state.paths.inputs_dir, "assets.json"), ReferenceAssets)
        approval_payload = self._load_optional_model(os.path.join(state.paths.intermediate_dir, "approval_payload.json"), ApprovalPayload)
        outputs = self._load_optional_model(os.path.join(state.paths.exports_dir, "outputs.json"), CarouselOutput)
        qa_report = self._load_optional_model(os.path.join(state.paths.intermediate_dir, "qa_report.json"), QaReport)
        asset_manifest = read_json_if_exists(os.path.join(state.paths.intermediate_dir, "asset_manifest.json")) or {}
        approved_raw = read_json_if_exists(os.path.join(state.paths.intermediate_dir, "approved_slides.json")) or []
        approved_slides = [TypedSlide.model_validate(item) for item in approved_raw]
        return CarouselJobDetailResponse(
            job=state,
            config=config,
            assets=assets,
            approval_payload=approval_payload,
            approved_slides=approved_slides,
            asset_manifest=asset_manifest,
            outputs=outputs,
            qa_report=qa_report,
        )
