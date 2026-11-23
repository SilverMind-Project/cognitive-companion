"""Result returned by knowledge delivery calls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivery_id: int | None = None
    session_id: int | None = None
