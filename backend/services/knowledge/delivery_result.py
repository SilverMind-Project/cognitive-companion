"""Result returned by knowledge delivery calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivery_id: int | None = None
    session_id: int | None = None
    # When an interactive session that is still open times out.
    timeout_at: datetime | None = None
