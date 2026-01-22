import os
import subprocess
import json

from app.core.settings import settings
from app.schemas import TextOverlayConfig
from app.services.storage_service import ensure_dir


def _wrap_text(text: str, max_words_per_line: int) -> str:
    words = text.split()
    if not words or max_words_per_line <= 0:
        return text
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        current.append(w)
        if len(current) >= max_words_per_line:
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)




def _normalize_ffmpeg_color(color: str) -> str:
    c = (color or "").strip()
    if c.startswith("#") and len(c) == 7:
        return "0x" + c[1:]
    return c or "white"


def _escape_drawtext_value(value: str) -> str:
    # Escape for ffmpeg drawtext when using ":" as option separator.
    # Keep it conservative and predictable.
    s = value.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "")
    return s


def _probe_video_size(path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    data = json.loads(out.decode("utf-8"))
    stream = (data.get("streams") or [{}])[0]
    w = int(stream.get("width") or 0)
    h = int(stream.get("height") or 0)
    if w <= 0 or h <= 0:
        raise RuntimeError("ffprobe could not determine video width/height")
    return w, h


def _count_non_whitespace_chars(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _estimate_text_box_pixels(
    wrapped_text: str,
    *,
    font_size: int,
    line_spacing: int,
) -> tuple[float, float]:
    # Rough model (works well enough for auto-fit heuristics):
    # - avg glyph width  ~= 0.55 * font_size
    # - avg glyph height ~= 1.15 * font_size
    lines = wrapped_text.splitlines() or [wrapped_text]
    max_line_len = max((len(line) for line in lines), default=0)
    w = max_line_len * (font_size * 0.55)
    h = (len(lines) * (font_size * 1.15)) + (max(0, len(lines) - 1) * line_spacing)
    return w, h


def _estimate_text_coverage_pct(
    *,
    video_width: int,
    video_height: int,
    text: str,
    font_size: int,
) -> float:
    # "Coverage" = total area of letters vs full video area (approx).
    # Area(1 char) ~= (0.55 * fs) * (1.15 * fs)
    letters = _count_non_whitespace_chars(text)
    if letters <= 0:
        return 0.0
    video_area = max(1, video_width * video_height)
    char_area = (0.55 * float(font_size)) * (1.15 * float(font_size))
    return (letters * char_area) / float(video_area) * 100.0


def _compute_auto_words_per_line(config: TextOverlayConfig, *, video_width: int, font_size: int) -> int:
    padding_pixels = int(video_width * float(config.padding_pct or 0.0) / 100.0)
    usable_width = max(1, video_width - 2 * padding_pixels)
    avg_char_width = max(1.0, float(font_size) * 0.45)
    max_chars = max(1, int(usable_width / avg_char_width))
    words = config.text.split()
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 5.0
    avg_word_len = max(1.0, avg_word_len)
    return max(1, int(max_chars / (avg_word_len + 1)))


def _compute_position(cfg: TextOverlayConfig) -> tuple[str, str]:
    # center_x is horizontal anchor (left/center/right), center_y now refers to the top edge of the text block.
    cx = cfg.center_x
    cy = cfg.center_y
    if cfg.align == "center":
        x_expr = f"w*{cx}-text_w/2"
    elif cfg.align == "left":
        x_expr = f"w*{cx}"
    else:  # right
        x_expr = f"w*{cx}-text_w"
    y_expr = f"h*{cy}"
    return x_expr, y_expr


class TextOverlayService:
    """Service to apply text overlay on existing videos using ffmpeg drawtext."""

    def _fits_in_frame(
        self,
        *,
        video_width: int,
        video_height: int,
        padding_x: int,
        padding_y: int,
        cfg: TextOverlayConfig,
        box_w: float,
        box_h: float,
    ) -> bool:
        # Position constraints are approximated using the same box model as _estimate_text_box_pixels.
        cx_px = float(cfg.center_x) * float(video_width)
        cy_px = float(cfg.center_y) * float(video_height)  # top edge

        left_limit = float(padding_x)
        right_limit = float(video_width - padding_x)
        top_limit = float(padding_y)
        bottom_limit = float(video_height - padding_y)

        if cfg.align == "center":
            left = cx_px - box_w / 2.0
            right = cx_px + box_w / 2.0
        elif cfg.align == "left":
            left = cx_px
            right = cx_px + box_w
        else:  # right
            left = cx_px - box_w
            right = cx_px

        top = cy_px
        bottom = cy_px + box_h

        return left >= left_limit and right <= right_limit and top >= top_limit and bottom <= bottom_limit

    def _build_drawtext_filter(self, render_config: TextOverlayConfig) -> str:
        wrapped = _wrap_text(render_config.text, render_config.max_words_per_line)
        text_for_filter = wrapped # Не применять escape_drawtext_value, т.к. это не нужно
        x_expr, y_expr = _compute_position(render_config)
        align_map = {"left": "L+M", "center": "C+M", "right": "R+M"}
        text_align = align_map.get(render_config.align, "C+M")

        font_color = _normalize_ffmpeg_color(render_config.font_color)
        outline_color = _normalize_ffmpeg_color(render_config.outline_color)
        fontfile = render_config.font_path or settings.DRAW_TEXT_FONT_PATH
        fontfile = _escape_drawtext_value(fontfile)

        draw_opts = [
            f"fontfile='{fontfile}'",
            f"text='{text_for_filter}'",
            "box=1",
            "boxcolor=0x000000@0.0",
            "boxborderw=0",
            f"text_align={text_align}",
            f"fontsize={render_config.font_size}",
            f"fontcolor={font_color}",
            f"line_spacing={render_config.line_spacing}",
            f"bordercolor={outline_color}",
            f"borderw={render_config.outline_width}",
            f"x={x_expr}",
            f"y={y_expr}",
        ]
        return "drawtext=" + ":".join(draw_opts)

    def apply_texts_on_video(
        self,
        input_video: str,
        configs: list[TextOverlayConfig],
        *,
        output_path: str,
    ) -> str:
        if not os.path.exists(input_video):
            raise FileNotFoundError(f"Input video not found: {input_video}")
        if not configs:
            raise ValueError("configs must be non-empty")

        base_dir = os.path.dirname(output_path) or os.path.dirname(input_video) or settings.DATA_DIR
        ensure_dir(base_dir)

        render_configs: list[TextOverlayConfig] = []
        for cfg in configs:
            render_cfg = self._auto_fit_by_coverage(input_video, cfg) if cfg.auto_fit else cfg
            render_configs.append(render_cfg)

        vf = ",".join(self._build_drawtext_filter(rc) for rc in render_configs)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_video,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            output_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path

    def apply_topic_title_and_description(
        self,
        input_video: str,
        *,
        title_cfg: TextOverlayConfig,
        description_cfg: TextOverlayConfig,
        output_path: str,
        description_gap_px: int | None = None,
    ) -> str:
        vw, vh = _probe_video_size(input_video)

        fitted_title = self._auto_fit_by_coverage(input_video, title_cfg) if title_cfg.auto_fit else title_cfg
        title_wrapped = _wrap_text(fitted_title.text, fitted_title.max_words_per_line)
        _, title_box_h = _estimate_text_box_pixels(
            title_wrapped,
            font_size=int(fitted_title.font_size),
            line_spacing=int(fitted_title.line_spacing),
        )

        gap_px = int(description_gap_px) if description_gap_px is not None else int(fitted_title.font_size * 0.55 + 8)
        desc_y = float(fitted_title.center_y) + (float(title_box_h) + float(gap_px)) / float(max(1, vh))
        desc_y = max(0.0, min(desc_y, 1.0))

        prepared_desc = description_cfg.model_copy(update={"center_y": desc_y})
        fitted_desc = self._auto_fit_by_coverage(input_video, prepared_desc) if prepared_desc.auto_fit else prepared_desc

        # Ensure description fits in visible area with padding
        padding_y = int(vh * float(fitted_desc.padding_pct or 0.0) / 100.0)
        _, desc_box_h = _estimate_text_box_pixels(
            _wrap_text(fitted_desc.text, fitted_desc.max_words_per_line),
            font_size=int(fitted_desc.font_size),
            line_spacing=int(fitted_desc.line_spacing),
        )
        max_top = max(0.0, 1.0 - (float(padding_y) + float(desc_box_h)) / float(max(1, vh)))
        if fitted_desc.center_y > max_top:
            fitted_desc = fitted_desc.model_copy(update={"center_y": max_top})

        return self.apply_texts_on_video(
            input_video,
            [fitted_title, fitted_desc],
            output_path=output_path,
        )

    def _auto_fit_by_coverage(self, input_video: str, config: TextOverlayConfig) -> TextOverlayConfig:
        vw, vh = _probe_video_size(input_video)
        padding_x = int(vw * float(config.padding_pct or 0.0) / 100.0)
        padding_y = int(vh * float(config.padding_pct or 0.0) / 100.0)
        usable_w = max(1, vw - 2 * padding_x)
        usable_h = max(1, vh - 2 * padding_y)

        start_fs = int(config.auto_fit_base_font_size or config.font_size)
        min_fs = int(config.auto_fit_min_font_size)
        min_fs = max(1, min(min_fs, start_fs))

        min_pct = float(config.min_text_coverage_pct or 0.0)
        max_pct = float(config.max_text_coverage_pct or 0.0)
        min_pct = max(0.0, min(min_pct, max_pct))

        min_words = max(1, int(config.auto_fit_min_words_per_line))
        max_words = max(min_words, int(config.auto_fit_max_words_per_line))
        reached_max_words = False
        current_words = min_words

        candidates: list[tuple[int, int, float]] = []

        for fs in range(start_fs, min_fs - 1, -1):
            computed_words = _compute_auto_words_per_line(config, video_width=vw, font_size=fs)
            allowed_words = max(min_words, min(max_words, computed_words))
            if not reached_max_words:
                current_words = max(current_words, allowed_words)
                if current_words >= max_words:
                    current_words = max_words
                    reached_max_words = True
            else:
                current_words = max_words

            wrapped = _wrap_text(config.text, current_words)
            coverage = _estimate_text_coverage_pct(
                video_width=vw,
                video_height=vh,
                text=wrapped,
                font_size=fs,
            )
            box_w, box_h = _estimate_text_box_pixels(wrapped, font_size=fs, line_spacing=int(config.line_spacing))

            if box_w > usable_w or box_h > usable_h:
                continue

            if not self._fits_in_frame(
                video_width=vw,
                video_height=vh,
                padding_x=padding_x,
                padding_y=padding_y,
                cfg=config,
                box_w=box_w,
                box_h=box_h,
            ):
                continue

            candidates.append((fs, current_words, coverage))

            if min_pct <= coverage <= max_pct:
                return config.model_copy(update={"font_size": fs, "max_words_per_line": current_words})

        if not candidates:
            return config

        under_max = next((c for c in candidates if c[2] <= max_pct), None)
        if under_max:
            chosen_fs, chosen_words, _ = under_max
            return config.model_copy(update={"font_size": chosen_fs, "max_words_per_line": chosen_words})

        chosen_fs, chosen_words, _ = candidates[-1]
        return config.model_copy(update={"font_size": chosen_fs, "max_words_per_line": chosen_words})


    def apply_text_on_video(
        self,
        input_video: str,
        config: TextOverlayConfig,
        *,
        output_path: str | None = None,
    ) -> str:
        if not os.path.exists(input_video):
            raise FileNotFoundError(f"Input video not found: {input_video}")

        base_dir = os.path.dirname(output_path) if output_path else os.path.dirname(input_video)
        if not base_dir:
            base_dir = settings.DATA_DIR
        ensure_dir(base_dir)

        if output_path is None:
            base_name = os.path.basename(input_video)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(base_dir, f"{name}_text{ext or '.mp4'}")

        render_config = self._auto_fit_by_coverage(input_video, config) if config.auto_fit else config
        return self.apply_texts_on_video(input_video, [render_config], output_path=output_path)


