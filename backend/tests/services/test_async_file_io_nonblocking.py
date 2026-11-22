"""Tests proving local file reads in async helpers do not block the event loop."""

from __future__ import annotations

import asyncio
import base64
import threading

import pytest

from backend.integrations.llm import base as llm_base
from backend.services import person_tracking


@pytest.mark.asyncio
async def test_encode_image_data_uri_runs_disk_read_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    payload = b"\xff\xd8\xff\xe0test-jpeg"

    def _blocking_read(_path: str) -> bytes:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5.0), "event loop was blocked and never released worker thread"
        return payload

    monkeypatch.setattr(llm_base, "_read_bytes_sync", _blocking_read)

    encode_task = asyncio.create_task(llm_base.encode_image_data_uri("/tmp/sample.jpg"))
    await asyncio.wait_for(started.wait(), timeout=5.0)

    # Prove the event loop can schedule and complete another coroutine while I/O is blocked.
    ran_concurrently = False

    async def _peer_task() -> None:
        nonlocal ran_concurrently
        ran_concurrently = True
        release.set()

    await asyncio.create_task(_peer_task())
    uri = await encode_task

    assert ran_concurrently is True
    expected = f"data:image/jpeg;base64,{base64.b64encode(payload).decode()}"
    assert uri == expected


@pytest.mark.asyncio
async def test_person_tracking_load_images_runs_disk_read_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    payload = b"frame-bytes"

    def _blocking_read(_path: str) -> bytes:
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5.0), "event loop was blocked and never released worker thread"
        return payload

    monkeypatch.setattr(person_tracking, "_read_bytes_sync", _blocking_read)

    load_task = asyncio.create_task(
        person_tracking.PersonTrackingService._load_images_as_base64(["/tmp/frame.jpg"])
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)

    ran_concurrently = False

    async def _peer_task() -> None:
        nonlocal ran_concurrently
        ran_concurrently = True
        release.set()

    await asyncio.create_task(_peer_task())
    encoded = await load_task

    assert ran_concurrently is True
    assert encoded == [base64.b64encode(payload).decode("utf-8")]
