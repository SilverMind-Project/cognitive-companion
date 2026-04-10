"""
Media processing utilities -- video down-sampling, frame extraction,
and image encoding.

Uses subprocess calls to ffmpeg/ffprobe for video operations and
Pillow for image handling. No ffmpeg-python dependency required.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import subprocess

from PIL import Image

from backend.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Video processing
# ---------------------------------------------------------------------------


async def process_video(
    input_path: str,
    output_path: str,
    fps: int = 2,
    target_height: int = 720,
) -> str:
    """Down-sample a video to *fps* FPS and scale to *target_height*."""
    logger.info(
        "process_video_start",
        input=input_path,
        output=output_path,
        fps=fps,
        target_height=target_height,
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"fps={fps},scale=-2:{target_height}",
        "-vcodec", "libx264",
        "-crf", "23",
        "-preset", "fast",
        output_path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        err_msg = stderr.decode(errors="replace")
        logger.error("process_video_failed", error=err_msg)
        raise RuntimeError(f"ffmpeg failed (rc={process.returncode}): {err_msg}")

    logger.info("process_video_done", output=output_path)
    return output_path


def get_video_info(input_path: str) -> dict:
    """Return basic metadata for a video file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    probe = json.loads(result.stdout)
    video_stream = next(
        (s for s in probe.get("streams", []) if s["codec_type"] == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError(f"No video stream found in {input_path}")

    raw_frames = video_stream.get("nb_frames")
    nb_frames = int(raw_frames) if raw_frames else 0

    duration_str = video_stream.get("duration") or probe.get("format", {}).get(
        "duration", "0"
    )

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "nb_frames": nb_frames,
        "duration": float(duration_str),
        "codec": video_stream.get("codec_name", "unknown"),
    }


async def extract_frames(
    input_path: str,
    max_frames: int = 20,
) -> list[str]:
    """Extract evenly-spaced frames from a video as base64 JPEG strings."""
    logger.info("extract_frames_start", path=input_path, max_frames=max_frames)

    info = get_video_info(input_path)
    total_frames = info["nb_frames"]

    if total_frames <= 0:
        total_frames = int(info["duration"] * 30)
    if total_frames <= 0:
        total_frames = max_frames

    step = max(1, math.ceil(total_frames / max_frames))
    indices = list(range(0, total_frames, step))[:max_frames]
    select_expr = "+".join(f"eq(n\\,{i})" for i in indices)

    width, height = info["width"], info["height"]

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"select='{select_expr}'",
        "-vsync", "vfr",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "pipe:1",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        err_msg = stderr.decode(errors="replace")
        logger.error("extract_frames_ffmpeg_failed", error=err_msg)
        raise RuntimeError(f"ffmpeg frame extraction failed: {err_msg}")

    frame_size = width * height * 3
    num_frames_extracted = len(stdout) // frame_size

    frames_b64: list[str] = []
    for i in range(num_frames_extracted):
        raw = stdout[i * frame_size : (i + 1) * frame_size]
        img = Image.frombytes("RGB", (width, height), raw)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        frames_b64.append(base64.b64encode(buf.getvalue()).decode())

    logger.info("extract_frames_done", count=len(frames_b64))
    return frames_b64


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def encode_image_base64(path: str) -> str:
    """Read an image file and return its contents as a base64 JPEG string."""
    try:
        img = Image.open(path)
        img.load()
    except Exception:
        logger.exception("encode_image_base64_open_failed", path=path)
        raise

    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")  # type: ignore[assignment]
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()
