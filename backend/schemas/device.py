"""Pydantic wire models for device/reCamera endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ReCameraData(BaseModel):
    image: str  # base64-encoded JPEG
    labels: list[str] = []
    boxes: list[list[int | float]] = []
    count: int = 0
    perf: list[list[int | float]] = []
    resolution: list[int] = []


class ReCameraPayload(BaseModel):
    code: int = 0
    data: ReCameraData
    name: str = ""
    type: int = 0
