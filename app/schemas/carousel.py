from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


CarouselLang = Literal["ru", "en", "auto"]
CarouselOutputFormat = Literal["png", "jpg"]
HighlightStyle = Literal["fill", "underline", "glow"]
HeroSide = Literal["left", "right"]
HeroLayout = Literal["off", "left", "right"]
AUTO_FONT_NAME = "AUTO"
LayoutPresetName = Literal["hero_left", "hero_right", "text_only", "cards_grid"]
SlideType = Literal["cover", "content", "cta", "hook", "explanation", "mistakes", "examples", "action_steps", "checklist", "summary"]
TextRole = Literal["title", "body", "bullet", "caption", "cta", "subtitle"]


class CanvasSize(BaseModel):
    w: int = Field(default=1080, ge=1080, le=1080)
    h: int = Field(default=1350, ge=1350, le=1350)


class SafeMargins(BaseModel):
    top: int = Field(default=96, ge=0, le=400)
    bottom: int = Field(default=96, ge=0, le=400)
    left: int = Field(default=84, ge=0, le=400)
    right: int = Field(default=84, ge=0, le=400)


class StyleVars(BaseModel):
    canvas_w: int = Field(default=1080, ge=1080, le=1080)
    canvas_h: int = Field(default=1350, ge=1350, le=1350)
    safe_top: int = Field(default=96, ge=0, le=400)
    safe_bottom: int = Field(default=96, ge=0, le=400)
    safe_left: int = Field(default=84, ge=0, le=400)
    safe_right: int = Field(default=84, ge=0, le=400)
    export_format: CarouselOutputFormat = "png"
    jpg_quality: int = Field(default=92, ge=60, le=100)

    color_bg: str = "#050816"
    color_text_main: str = "#F8FAFC"
    color_text_muted: str = "#CBD5E1"
    color_accent: str = "#39FF88"
    color_accent_2: str = "#38BDF8"
    color_cta_bar: str = "#0F172A"
    highlight_style: HighlightStyle = "glow"

    font_h1_family: str = AUTO_FONT_NAME
    font_subtitle_family: str = AUTO_FONT_NAME
    font_body_family: str = AUTO_FONT_NAME
    font_h1_weight: int = Field(default=700, ge=300, le=900)
    font_body_weight: int = Field(default=500, ge=300, le=900)
    font_h1_size: int = Field(default=84, ge=24, le=180)
    font_body_size: int = Field(default=40, ge=16, le=96)
    font_caption_size: int = Field(default=32, ge=14, le=80)
    line_height_h1: float = Field(default=1.02, ge=0.8, le=2.0)
    line_height_body: float = Field(default=1.24, ge=0.9, le=2.0)
    letter_spacing_h1: int = Field(default=0, ge=-4, le=20)
    text_stroke_width: int = Field(default=2, ge=0, le=20)
    text_stroke_color: str = "#020617"
    text_shadow_xy: int = Field(default=4, ge=0, le=80)
    text_shadow_blur: int = Field(default=18, ge=0, le=100)
    text_shadow_color: str = "#020617"
    text_glow_intensity: int = Field(default=16, ge=0, le=100)

    fx_vignette_intensity: float = Field(default=0.18, ge=0.0, le=1.0)
    fx_grain_amount: float = Field(default=0.035, ge=0.0, le=1.0)
    fx_lightning_density: float = Field(default=0.25, ge=0.0, le=1.0)
    fx_lightning_thickness: int = Field(default=4, ge=1, le=40)
    fx_neon_blur: int = Field(default=18, ge=0, le=100)
    fx_neon_line_width: int = Field(default=5, ge=1, le=40)

    hero_layout: HeroLayout = "off"
    hero_slides: list[int] = Field(default_factory=lambda: [1], max_length=20)

    layout_preset: LayoutPresetName = "hero_right"
    hero_enabled: bool = True
    hero_side: HeroSide = "right"
    hero_slide_indices: list[int] = Field(default_factory=lambda: [1], max_length=20)
    hero_scale: float = Field(default=1.0, ge=0.3, le=2.0)
    card_radius: int = Field(default=28, ge=0, le=120)
    card_shadow: int = Field(default=28, ge=0, le=120)
    card_stroke: int = Field(default=1, ge=0, le=12)
    text_card_outline_enabled: bool = False
    allow_illustration_on_last_slide: bool = False
    cta_enabled: bool = True
    cta_text: str = "Сохраните карусель и возвращайтесь"
    cta_position: str = Field(default="bottom", pattern="^(top|bottom)$")

    @model_validator(mode="after")
    def _sync_hero_fields(self) -> "StyleVars":
        normalized_slides = sorted({idx for idx in self.hero_slides if 1 <= idx <= 20})
        self.hero_slides = normalized_slides or [1]

        if self.hero_layout == "off" and (self.hero_enabled or self.layout_preset in {"hero_left", "hero_right"}):
            if self.layout_preset in {"hero_left", "hero_right"}:
                self.hero_layout = "left" if self.layout_preset == "hero_left" else "right"
            else:
                self.hero_layout = "left" if self.hero_side == "left" else "right"

        if self.hero_layout == "off":
            self.hero_enabled = False
            self.layout_preset = "text_only"
        else:
            self.hero_enabled = True
            self.hero_side = "left" if self.hero_layout == "left" else "right"
            self.layout_preset = "hero_left" if self.hero_layout == "left" else "hero_right"
        return self


class CarouselJobConfig(BaseModel):
    canvas: CanvasSize = Field(default_factory=CanvasSize)
    lang: CarouselLang = "ru"
    slide_count: int = Field(default=7, ge=1, le=20)
    has_user_text: bool = False
    has_subject_image: bool = False
    ref_count: int = Field(default=0, ge=0, le=5)
    output_format: CarouselOutputFormat = "png"
    safe_margins: SafeMargins = Field(default_factory=SafeMargins)
    style_vars: StyleVars = Field(default_factory=StyleVars)


class CarouselCreateRequest(BaseModel):
    topic: str = Field(default="", max_length=300)
    lang: CarouselLang = "auto"
    slide_count: int = Field(default=7, ge=1, le=20)
    user_text: str | None = Field(default=None, max_length=10000)
    style_vars: StyleVars = Field(default_factory=StyleVars)


class StoredAsset(BaseModel):
    name: str
    original_name: str
    path: str
    media_type: str | None = None
    size_bytes: int | None = None


class CarouselJobPaths(BaseModel):
    root: str
    inputs_dir: str
    intermediate_dir: str
    assets_dir: str
    slides_dir: str
    exports_dir: str
    debug_slides_dir: str = ""


class CarouselJobState(BaseModel):
    job_id: str
    status: Literal["created", "draft_ready", "approved", "rendering", "completed", "failed"] = "created"
    error: str | None = None
    current_step: str = "created"
    paths: CarouselJobPaths
    created_at: str
    updated_at: str


class ReferenceAssets(BaseModel):
    ref_style_images: list[StoredAsset] = Field(default_factory=list, max_length=5)
    subject_image: StoredAsset | None = None
    brand_assets: list[StoredAsset] = Field(default_factory=list)


class DraftSlide(BaseModel):
    slide_type: SlideType = "content"
    title: str = Field(..., max_length=1000)
    body: list[str] = Field(default_factory=list, max_length=6)
    bullets: list[str] = Field(default_factory=list, min_length=0, max_length=6)
    emphasis_words: list[str] = Field(default_factory=list, max_length=12)
    cta: str | None = Field(default=None, max_length=1000)


class TextBlock(BaseModel):
    text: str
    max_lines: int = Field(default=2, ge=1, le=12)
    role: TextRole = "title"


class TypedSlide(BaseModel):
    id: str
    slide_type: SlideType = "content"
    title_block: TextBlock
    body_blocks: list[TextBlock] = Field(default_factory=list, max_length=6)
    bullet_blocks: list[TextBlock] = Field(default_factory=list, max_length=6)
    emphasis_spans: list[str] = Field(default_factory=list, max_length=12)
    cta: str | None = Field(default=None, max_length=1000)


class TypedSlidesReview(BaseModel):
    typed_slides_checked: list[TypedSlide] = Field(default_factory=list)
    issues_fixed: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)


class ApprovalSlide(BaseModel):
    id: str
    title: str = Field(..., max_length=1000)
    body: list[str] = Field(default_factory=list, max_length=6)
    bullets: list[str] = Field(default_factory=list, max_length=6)
    emphasis_words: list[str] = Field(default_factory=list, max_length=12)
    cta: str | None = Field(default=None, max_length=1000)


class EditRules(BaseModel):
    title_max_chars: int = 70
    bullets_min: int = 0
    bullets_max: int = 6
    bullet_max_chars: int = 90
    emphasis_max_items: int = 12
    cta_max_chars: int = 90


class ApprovalPayload(BaseModel):
    lang: CarouselLang = "ru"
    slides: list[ApprovalSlide] = Field(default_factory=list)
    edit_rules: EditRules = Field(default_factory=EditRules)


class ApprovalSubmitRequest(BaseModel):
    slides: list[ApprovalSlide] = Field(default_factory=list)


class PaletteTokens(BaseModel):
    bg: str
    text: str
    accent: str
    accent2: str
    muted: str
    cta_bar: str


class CarouselFontOption(BaseModel):
    id: str
    name: str
    filename: str
    url: str


class FontTokens(BaseModel):
    h1: str
    subtitle: str = AUTO_FONT_NAME
    body: str


class EffectTokens(BaseModel):
    glow: int
    grain: float
    vignette: float
    lightning: float


class ShapeTokens(BaseModel):
    radius: int
    stroke: int


class DesignTokens(BaseModel):
    palette: PaletteTokens
    fonts: FontTokens
    effects: EffectTokens
    shape: ShapeTokens


class BBox(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class LayoutTemplate(BaseModel):
    name: LayoutPresetName
    title_box: BBox
    bullet_box: BBox
    hero_box: BBox | None = None
    cta_box: BBox | None = None
    illustration_boxes: list[BBox] = Field(default_factory=list)
    clean_zones: list[BBox] = Field(default_factory=list)


class FontPlan(BaseModel):
    primary_font: str
    subtitle_font: str = ""
    fallback_font: str
    weights: dict[str, int] = Field(default_factory=dict)
    supports: dict[str, bool] = Field(default_factory=dict)


class LayerPlacement(BaseModel):
    name: str
    bbox: BBox | None = None
    path: str | None = None
    meta: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SlideLayerMap(BaseModel):
    slide_id: str
    layers: list[LayerPlacement] = Field(default_factory=list)


class SlideRenderResult(BaseModel):
    slide_id: str
    slide_path: str
    layer_map: SlideLayerMap
    template_name: LayoutPresetName
    overflow_warnings: list["OverflowWarning"] = Field(default_factory=list)


class SlideTextChange(BaseModel):
    field: str
    before: str | None = None
    after: str | None = None
    exact_changed: bool = False
    normalized_changed: bool = False


class SlideTextDiff(BaseModel):
    slide_id: str
    changes: list[SlideTextChange] = Field(default_factory=list)


class OverflowWarning(BaseModel):
    slide_id: str
    block_role: Literal["title", "body", "bullet", "cta"]
    original_text: str
    rendered_text: str
    fit_size: int
    min_allowed_size: int
    box: BBox


class TextChangeReport(BaseModel):
    has_changes: bool = False
    change_count: int = 0
    slides: list[SlideTextDiff] = Field(default_factory=list)
    overflow_warnings: list[OverflowWarning] = Field(default_factory=list)


class QaIssue(BaseModel):
    kind: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class SlideQaReport(BaseModel):
    slide_id: str
    ok: bool = True
    issues: list[QaIssue] = Field(default_factory=list)
    fixes_applied: list[str] = Field(default_factory=list)
    final_slide_path: str


class QaReport(BaseModel):
    overall_ok: bool = True
    slides: list[SlideQaReport] = Field(default_factory=list)


class JobSpec(BaseModel):
    job_id: str
    config: CarouselJobConfig
    approved_slides: list[TypedSlide] = Field(default_factory=list)
    design_tokens: DesignTokens
    layout_templates: list[LayoutTemplate] = Field(default_factory=list)
    font_plan: FontPlan
    asset_manifest: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    qa_report: QaReport


class CarouselJobResponse(BaseModel):
    job_id: str
    status: str
    config: CarouselJobConfig
    assets: ReferenceAssets


class CarouselDraftResponse(BaseModel):
    job_id: str
    status: str
    approval_payload: ApprovalPayload
    text_change_report: TextChangeReport | None = None


class CarouselApproveResponse(BaseModel):
    job_id: str
    status: str
    typed_slides: list[TypedSlide] = Field(default_factory=list)
    text_change_report: TextChangeReport | None = None


class CarouselOutput(BaseModel):
    slide_paths: list[str] = Field(default_factory=list)
    preview_strip_path: str | None = None
    job_spec_path: str | None = None
    zip_path: str | None = None


class CarouselRenderResponse(BaseModel):
    job_id: str
    status: str
    outputs: CarouselOutput
    qa_report: QaReport
    text_change_report: TextChangeReport | None = None


class CarouselJobDetailResponse(BaseModel):
    job: CarouselJobState
    config: CarouselJobConfig | None = None
    assets: ReferenceAssets | None = None
    approval_payload: ApprovalPayload | None = None
    approved_slides: list[TypedSlide] = Field(default_factory=list)
    asset_manifest: dict[str, Any] = Field(default_factory=dict)
    outputs: CarouselOutput | None = None
    qa_report: QaReport | None = None
    text_change_report: TextChangeReport | None = None
