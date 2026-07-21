"""Visitor cluster admin BFF envelopes (identity-continuity M07).

person-identification-service (M06) owns the visitor cluster lifecycle:
persisted unmatched face embeddings, incremental clustering, surfacing, and
naming. The BFF validates the upstream envelope, presigns crop media, and
orchestrates the two-system naming transaction (face-service member, then the
CC household member); it never re-derives clustering or surfacing decisions.

Only the ``name`` action is a mutation of substance: it moves biometric data
from the visitor dataset into the governed enrollment dataset. Dismiss and
merge only affect the review queue.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VisitorClusterStatus = Literal["candidate", "surfaced", "named", "dismissed"]


class VisitorSightingView(BaseModel):
    seen_at: datetime
    quality: float
    crop_object: str | None = None
    crop_url: str | None = None


class VisitorClusterView(BaseModel):
    cluster_id: str
    status: VisitorClusterStatus
    display_hint: str | None = None
    named_person_id: str | None = None
    sighting_count: int
    distinct_days: int
    first_seen_at: datetime
    last_seen_at: datetime
    recent_crop_urls: list[str] = Field(default_factory=list)


class VisitorClusterDetailView(BaseModel):
    cluster: VisitorClusterView
    recent_sightings: list[VisitorSightingView] = Field(default_factory=list)


class VisitorClusterListResponse(BaseModel):
    clusters: list[VisitorClusterView]
    total: int


class NameVisitorRequest(BaseModel):
    model_config = {"extra": "forbid"}

    person_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)


class NameVisitorResponse(BaseModel):
    cluster_id: str
    status: VisitorClusterStatus
    named_person_id: str
    member_name: str
    embedding_count: int
    household_member_created: bool


class DismissVisitorResponse(BaseModel):
    cluster_id: str
    status: VisitorClusterStatus
