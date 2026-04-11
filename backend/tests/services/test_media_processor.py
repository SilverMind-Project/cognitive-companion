"""Tests for ``backend.services.media_processor``.

ffmpeg/ffprobe are mocked via ``monkeypatch`` so these tests run without
external binaries. Pillow (pure-python) is used directly for image fixtures.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backend.services import media_processor as mp

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _write_jpeg(path: Path, size: tuple[int, int] = (32, 32)) -> None:
    Image.new("RGB", size, color=(255, 0, 0)).save(path, format="JPEG")


def _write_rgba_png(path: Path) -> None:
    Image.new("RGBA", (16, 16), color=(0, 255, 0, 128)).save(path, format="PNG")


# ---------------------------------------------------------------------------
# process_video
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_video_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        captured["cmd"] = cmd
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)

    out = await mp.process_video(
        input_path=str(tmp_path / "in.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        fps=4,
        target_height=480,
    )
    assert out == str(tmp_path / "out.mp4")
    assert "ffmpeg" in captured["cmd"][0]
    assert "fps=4,scale=-2:480" in captured["cmd"]


@pytest.mark.asyncio
async def test_process_video_failure_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        return _FakeProcess(returncode=1, stderr=b"ffmpeg: bad input")

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        await mp.process_video(
            input_path=str(tmp_path / "in.mp4"),
            output_path=str(tmp_path / "out.mp4"),
        )


# ---------------------------------------------------------------------------
# get_video_info
# ---------------------------------------------------------------------------


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _probe_json(
    width: int = 640,
    height: int = 480,
    nb_frames: str | None = "300",
    duration: str | None = "10.0",
    codec: str = "h264",
    include_video: bool = True,
    top_duration: str | None = None,
) -> str:
    streams: list[dict] = []
    if include_video:
        stream: dict[str, Any] = {
            "codec_type": "video",
            "width": width,
            "height": height,
            "codec_name": codec,
        }
        if nb_frames is not None:
            stream["nb_frames"] = nb_frames
        if duration is not None:
            stream["duration"] = duration
        streams.append(stream)
    body: dict[str, Any] = {"streams": streams}
    if top_duration is not None:
        body["format"] = {"duration": top_duration}
    return json.dumps(body)


def test_get_video_info_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda *a, **kw: _CompletedProcess(0, stdout=_probe_json()),
    )
    info = mp.get_video_info("x.mp4")
    assert info == {
        "width": 640,
        "height": 480,
        "nb_frames": 300,
        "duration": 10.0,
        "codec": "h264",
    }


def test_get_video_info_ffprobe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda *a, **kw: _CompletedProcess(1, stderr="bad file"),
    )
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        mp.get_video_info("x.mp4")


def test_get_video_info_no_video_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda *a, **kw: _CompletedProcess(0, stdout=_probe_json(include_video=False)),
    )
    with pytest.raises(ValueError, match="No video stream"):
        mp.get_video_info("x.mp4")


def test_get_video_info_missing_nb_frames_uses_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda *a, **kw: _CompletedProcess(0, stdout=_probe_json(nb_frames=None)),
    )
    info = mp.get_video_info("x.mp4")
    assert info["nb_frames"] == 0


def test_get_video_info_falls_back_to_format_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda *a, **kw: _CompletedProcess(
            0, stdout=_probe_json(duration=None, top_duration="42.5")
        ),
    )
    info = mp.get_video_info("x.mp4")
    assert info["duration"] == 42.5


# ---------------------------------------------------------------------------
# extract_frames
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_frames_decodes_jpegs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    width, height = 4, 4
    raw = bytes([255, 0, 0] * (width * height)) * 3  # 3 frames

    monkeypatch.setattr(
        mp,
        "get_video_info",
        lambda path: {
            "width": width,
            "height": height,
            "nb_frames": 3,
            "duration": 1.0,
            "codec": "h264",
        },
    )

    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        return _FakeProcess(returncode=0, stdout=raw)

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)

    frames = await mp.extract_frames("x.mp4", max_frames=3)
    assert len(frames) == 3
    # Each frame must decode back to a valid JPEG.
    for f in frames:
        img = Image.open(io.BytesIO(base64.b64decode(f)))
        img.load()
        assert img.size == (width, height)


@pytest.mark.asyncio
async def test_extract_frames_uses_duration_when_frames_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        mp,
        "get_video_info",
        lambda path: {
            "width": 2,
            "height": 2,
            "nb_frames": 0,
            "duration": 2.0,
            "codec": "h264",
        },
    )

    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        captured["cmd"] = cmd
        # 60 frames = duration * 30fps heuristic
        return _FakeProcess(returncode=0, stdout=b"\x00" * (2 * 2 * 3) * 5)

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)

    frames = await mp.extract_frames("x.mp4", max_frames=5)
    assert len(frames) == 5
    # select expression should reference frame indices
    assert any("select=" in str(arg) for arg in captured["cmd"])


@pytest.mark.asyncio
async def test_extract_frames_falls_back_to_max_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mp,
        "get_video_info",
        lambda path: {
            "width": 2,
            "height": 2,
            "nb_frames": 0,
            "duration": 0,
            "codec": "h264",
        },
    )

    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        return _FakeProcess(returncode=0, stdout=b"")

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)
    frames = await mp.extract_frames("x.mp4", max_frames=4)
    assert frames == []  # empty stdout -> zero frames extracted


@pytest.mark.asyncio
async def test_extract_frames_ffmpeg_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mp,
        "get_video_info",
        lambda path: {
            "width": 2,
            "height": 2,
            "nb_frames": 2,
            "duration": 1.0,
            "codec": "h264",
        },
    )

    async def _fake_exec(*cmd: str, **kwargs: Any) -> _FakeProcess:
        return _FakeProcess(returncode=2, stderr=b"oops")

    monkeypatch.setattr(mp.asyncio, "create_subprocess_exec", _fake_exec)

    with pytest.raises(RuntimeError, match="frame extraction failed"):
        await mp.extract_frames("x.mp4", max_frames=2)


# ---------------------------------------------------------------------------
# encode_image_base64
# ---------------------------------------------------------------------------


def test_encode_image_base64_jpeg_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "red.jpg"
    _write_jpeg(path)
    encoded = mp.encode_image_base64(str(path))
    decoded = base64.b64decode(encoded)
    img = Image.open(io.BytesIO(decoded))
    img.load()
    assert img.format == "JPEG"
    assert img.size == (32, 32)


def test_encode_image_base64_converts_rgba_to_rgb(tmp_path: Path) -> None:
    path = tmp_path / "alpha.png"
    _write_rgba_png(path)
    encoded = mp.encode_image_base64(str(path))
    img = Image.open(io.BytesIO(base64.b64decode(encoded)))
    img.load()
    assert img.mode == "RGB"
    assert img.format == "JPEG"


def test_encode_image_base64_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        mp.encode_image_base64(str(tmp_path / "does-not-exist.jpg"))
