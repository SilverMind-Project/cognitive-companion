"""Roster health BFF envelope.

Face identification matches each face to its nearest enrolled person, so a regular visitor who
was never enrolled is pulled toward whichever enrolled member they resemble most. Roster health
makes that risk visible: active household members without enough face enrollment, and recurring
unknown visitors waiting to be named or dismissed.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RosterMemberRef(BaseModel):
    member_id: str
    name: str
    embedding_count: int = Field(ge=0, description="Enrolled face embeddings; 0 if not enrolled")


class RosterHealthEnvelope(BaseModel):
    members_without_face_enrollment: list[RosterMemberRef] = Field(
        description=(
            "Active, non-guest household members with fewer than min_face_embeddings enrolled "
            "face embeddings"
        )
    )
    min_face_embeddings: int = Field(ge=1)
    visitor_clustering_enabled: bool
    surfaced_unnamed_visitor_clusters: int = Field(
        ge=0,
        description="Recurring unknown visitors awaiting naming or dismissal; 0 when disabled",
    )
    is_complete: bool = Field(
        description="True when no member lacks enrollment and no visitor cluster awaits review"
    )
    checked_at: datetime
