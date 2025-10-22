import os
import glob
import re
import tempfile
import subprocess

from app.services.storage_service import ensure_data_dir, get_frames_dir


def compose_video_from_frames(video_id: str, *, fps: int = 12, output_name: str = "frames_compose.mp4") -> str:
    """Create a video from previously saved frames for the given video_id.

    Returns the path to the composed mp4 inside data/<video_id>.
    """
    out_dir = ensure_data_dir(video_id)
    frames_dir = get_frames_dir(video_id)
    # Ensure there are frames
    frame_files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.jpg")))
    if not frame_files:
        raise RuntimeError("No frames found to compose a video")

    # ffmpeg expects an input pattern; to avoid quoting issues we run from frames_dir
    output_path = os.path.join(out_dir, output_name)
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        "frame_%05d.jpg",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, check=True, cwd=frames_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


def _extract_first_number(name: str) -> int | None:
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else None


def concatenate_videos_in_dir(input_dir: str, *, pattern: str = "*.mp4", output_name: str = "merged.mp4") -> str:
    """Concatenate all videos in a directory into a single mp4.

    Files are sorted by the first numeric value in the filename (ascending).
    If a filename does not contain digits, it is ordered lexicographically after numeric ones.

    Returns absolute path to the merged video saved in input_dir.
    """
    if not os.path.isdir(input_dir):
        raise RuntimeError(f"Input directory does not exist: {input_dir}")

    files = sorted(
        glob.glob(os.path.join(input_dir, pattern)),
        key=lambda p: (0, _extract_first_number(os.path.basename(p))) if _extract_first_number(os.path.basename(p)) is not None else (1, os.path.basename(p)),
    )
    if not files:
        raise RuntimeError("No input videos found to concatenate")

    output_path = os.path.join(input_dir, output_name)

    # Use concat demuxer with re-encode to ensure compatibility across inputs
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as list_file:
        list_path = list_file.name
        for p in files:
            list_file.write(f"file '{p}'\n")

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            output_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        try:
            os.remove(list_path)
        except Exception:
            pass

    return os.path.abspath(output_path)


def extract_last_frame(video_path: str, output_image_path: str) -> str:
    """Extract the last frame of a video into output_image_path (jpg)."""
    # Use ffmpeg to seek to end and extract last frame
    # -sseof -1 seeks 1 second from end; then select last frame
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-1",
        "-i",
        video_path,
        "-update",
        "1",
        "-q:v",
        "2",
        output_image_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_image_path


