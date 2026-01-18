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

        render_config = config
        if config.auto_fit:
            render_config = self._auto_fit_by_coverage(input_video, config)

        wrapped = _wrap_text(render_config.text, render_config.max_words_per_line)
        text_escaped = wrapped
        x_expr, y_expr = _compute_position(render_config)
        align_map = {
            "left": "L+M",
            "center": "C+M",
            "right": "R+M",
        }
        text_align = align_map.get(render_config.align, "C+M")

        # Common drawtext options
        text_for_filter = text_escaped
        font_color = _normalize_ffmpeg_color(render_config.font_color)
        outline_color = _normalize_ffmpeg_color(render_config.outline_color)
        draw_opts = [
            "fontfile=/home/alleftinna/python/FABRIC/data/fonts/Lorenzo Sans Bold.ttf",
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
        # if render_config.font_path:
        #     # NOTE: ffmpeg drawtext expects fontfile path; keep as-is (no custom escaping helper here).
        #     draw_opts.insert(0, f"fontfile='{render_config.font_path}'")

        drawtext = "drawtext=" + ":".join(draw_opts)
        print(drawtext)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_video,
            "-vf",
            drawtext,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            output_path,
        ]

        # Use subprocess with minimal shell involvement
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path


