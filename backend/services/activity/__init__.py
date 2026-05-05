"""Duration-aware activity domain service.

Consolidates :class:`~backend.services.person_tracking.PersonTrackingService.record_activity`
and :class:`~backend.services.activity_session.ActivitySessionService.open_session` /
`close_session` into a single domain surface.

No semantic-memory mirroring (per §2.5 of the refactor design doc).
"""

from __future__ import annotations

from backend.services.activity.service import ActivityService
from backend.services.activity.types import ActivityRecord, SessionRecord

__all__ = ["ActivityRecord", "ActivityService", "SessionRecord"]
