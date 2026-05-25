"""SQLAlchemy model for CTS dementia signals.

Signals are computed periodically by the tracking-orchestrator's
DementiaSignalWorker and persisted here in Cognitive Companion so the
dashboard can read them without hitting the orchestrator directly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.core.time import UTCDateTime


class DementiaSignal(Base):
    __tablename__ = "cts_dementia_signals"

    # Auto-incrementing primary key (mirrors the BigSerial from the
    # TimescaleDB schema in the orchestrator).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Deterministic signal ID from the orchestrator (UUID5).  Used to
    # detect re-upserts of the same logical signal window across worker runs.
    signal_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Person this signal belongs to (from the orchestrator).
    person_id: Mapped[str] = mapped_column(String(255), index=True)

    # Signal type: pacing, sundowning, bathroom_dwell_anomaly,
    # stillness, nighttime_movement, absence.
    signal_type: Mapped[str] = mapped_column(String(64), index=True)

    # Severity: info, warning, emergency.
    severity: Mapped[str] = mapped_column(String(16), index=True)

    # Time window the signal covers.
    window_start: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    window_end: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)

    # Computed signal value (e.g. number of room transitions for pacing).
    value: Mapped[float] = mapped_column(Float, nullable=False)

    # Baseline value for comparison (NULL if no baseline yet).
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Z-score relative to baseline (NULL if no baseline).
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Arbitrary context: room names, trajectory stats, etc.
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Detector algorithm version from the orchestrator (for filtering stale signals).
    algorithm_version: Mapped[int | None] = mapped_column(nullable=True, default=None)

    # Timestamp when a caregiver acknowledged this signal (NULL = unacknowledged).
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # When the signal was received by Cognitive Companion.
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
