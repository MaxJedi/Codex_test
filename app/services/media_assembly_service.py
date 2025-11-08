import os
import glob
import re
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

    # Robust concat using filter_complex (re-encode), tolerates differing codecs/containers
    cmd = ["ffmpeg", "-y"]
    for p in files:
        cmd += ["-i", p]

    # Build concat filter mapping both video and audio streams
    parts = []
    for i in range(len(files)):
        parts.append(f"[{i}:v:0][{i}:a:0]")
    filter_complex = "".join(parts) + f"concat=n={len(files)}:v=1:a=1[outv][outa]"
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Fallback: concatenate video only (ignore audio stream mismatches or absence)
        cmd_vo = ["ffmpeg", "-y"]
        for p in files:
            cmd_vo += ["-i", p]
        parts_vo = []
        for i in range(len(files)):
            parts_vo.append(f"[{i}:v:0]")
        filter_complex_vo = "".join(parts_vo) + f"concat=n={len(files)}:v=1:a=0[outv]"
        cmd_vo += [
            "-filter_complex", filter_complex_vo,
            "-map", "[outv]",
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        subprocess.run(cmd_vo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


