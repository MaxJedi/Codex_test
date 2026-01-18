import os
import subprocess
import json
from typing import Tuple

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


def _compute_auto_layout(config: TextOverlayConfig, video_width: int) -> tuple[int, int]:
    padding_pixels = int(video_width * float(config.padding_pct or 0.0) / 100.0)
    usable_width = max(1, video_width - 2 * padding_pixels)
    base_font = config.auto_fit_base_font_size or config.font_size
    avg_char_width = max(1, base_font * 0.45)
    max_chars = max(1, int(usable_width / avg_char_width))
    words = config.text.split()
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 5.0
    avg_word_len = max(1.0, avg_word_len)
    approximate_words = max(1, int(max_chars / (avg_word_len + 1)))
    return base_font, approximate_words


def _compute_position(cfg: TextOverlayConfig) -> Tuple[str, str]:
    # center_x, center_y in [0,1]
    cx = cfg.center_x
    cy = cfg.center_y
    if cfg.align == "center":
        x_expr = f"w*{cx}-text_w/2"
    elif cfg.align == "left":
        x_expr = f"w*{cx}"
    else:  # right
        x_expr = f"w*{cx}-text_w"
    y_expr = f"h*{cy}-text_h/2"
    return x_expr, y_expr


class TextOverlayService:
    """Service to apply text overlay on existing videos using ffmpeg drawtext."""

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
            vw, _ = _probe_video_size(input_video)
            layout_font_size, layout_words = _compute_auto_layout(config, vw)
            render_config = config.model_copy(update={
                "font_size": layout_font_size,
                "max_words_per_line": layout_words,
            })
        wrapped = _wrap_text(render_config.text, render_config.max_words_per_line)
        text_escaped = wrapped
        x_expr, y_expr = _compute_position(render_config)
        align_map = {
            "left": "L+M",
            "center": "C+M",
            "right": "R+M",
        }
        text_align = align_map.get(config.align, "C+M")

        # Common drawtext options
        text_for_filter = text_escaped
        font_color = _normalize_ffmpeg_color(config.font_color)
        outline_color = _normalize_ffmpeg_color(config.outline_color)
        print(f"text_for_filter: {text_for_filter}")
        draw_opts = [
            f"text='{text_for_filter}'",
            "box=1",
            "boxcolor=0x000000@0.0",
            "boxborderw=0",
            f"text_align={text_align}",
            f"fontsize={config.font_size}",
            f"fontcolor={font_color}",
            f"line_spacing={config.line_spacing}",
            f"bordercolor={outline_color}",
            f"borderw={config.outline_width}",
            f"x={x_expr}",
            f"y={y_expr}",
        ]
        if config.font_path:
            draw_opts.insert(0, f"fontfile={_escape_drawtext(config.font_path)}")

        drawtext = "drawtext=" + ":".join(draw_opts)

        if not config.auto_fit:
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
        else:
            # Auto-fit: render text with big fontsize on transparent layer and scale to max width.
            vw, vh = _probe_video_size(input_video)
            max_width = int(vw * (100.0 - 2.0 * float(config.padding_pct)) / 100.0)
            max_width = max(1, min(max_width, vw))
            base_fs = int(config.auto_fit_base_font_size)

            draw_opts_af = list(draw_opts)
            # Replace fontsize with base_fs for rendering before scaling
            draw_opts_af = [o if not o.startswith("fontsize=") else f"fontsize={base_fs}" for o in draw_opts_af]
            drawtext_af = "drawtext=" + ":".join(draw_opts_af)

            # Build filter_complex
            # 1) transparent layer (same aspect as video)
            # 2) drawtext on it
            # 3) scale layer to desired width (scale2ref)
            # 4) overlay on original video
            filter_complex = (
                f"color=c=black@0.0:s={vw}x{vh}[bg];"
                f"[bg]{drawtext_af}[txt];"
                f"[txt][0:v]scale2ref=w={max_width}:h=ow*ih/iw[scaled][vref];"
                f"[vref][scaled]overlay=x=W*{config.center_x}-w/2:y=H*{config.center_y}-h/2:format=auto[outv]"
            )

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                input_video,
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-map",
                "0:a?",
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


