"""EG-M14 D4 permission token vocabulary and route-to-token migration map.

Defines the closed D4 action set, the token regex, and the authoritative mapping
from every current ``(method, route_template, declared_token)`` to its target D4
``<resource>:<action>`` token. Used by both:

- ``backend/scripts/export_route_permissions.py`` to generate
  ``docs/api/permissions-migration.md`` and the ``M14-T`` approval table; and
- ``backend/core/auth.py`` during PR 2 shadow evaluation (so shadow checks use
  the exact target D4 token before PR 3 rewrites the 361 call sites).

Pure module with zero upward imports (``backend.core`` invariant).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Closed D4 action vocabulary (EG-M14 section 4).
# Adding an action is a reviewed edit to this constant.
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "read",
        "write",
        "delete",
        "execute",
        "import",
        "acknowledge",
        "propose",
        "correct",
        "calibrate",
        "review",
        "takeover",
        "act",
        "ingest",
        "heartbeat",
    }
)

D4_TOKEN_RE: re.Pattern[str] = re.compile(
    r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*:(" + "|".join(sorted(ALLOWED_ACTIONS)) + r")$"
)


def is_valid_d4_token(token: str) -> bool:
    """Return True iff *token* conforms to the closed D4 ``<resource>:<action>`` grammar."""
    return bool(D4_TOKEN_RE.match(token))


# Canonical clean role names in ``config/auth.yaml`` ``roles:`` (EG-M14 A4),
# mapped to the legacy ``permission_map`` entry names each key carries today.
ROLE_TO_LEGACY_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": ("admin",),
    "operator": ("operator",),
    "caregiver_admin": ("caregiver_admin",),
    "caregiver": ("caregiver",),
    "mcp_readonly": ("mcp_readonly",),
    "mcp_rules_import": ("rules:write_via_mcp",),
    "cts_ingress": ("cts_ingress",),
    "device_recamera": ("device:recamera",),
    "device_reterminal": ("device:reterminal", "image:read"),
}

# Target D4 tokens for the two WebSocket endpoints (authenticated inside handlers).
WS_ROUTE_TOKENS: dict[str, str] = {
    "/ws/cts": "cts.live:read",
    "/ws/pipeline": "pipeline.events:read",
}

# Reverse map for ``require_token`` call sites renamed in PR 3, so inverse shadow
# evaluation can still evaluate legacy ``permission_map`` membership during PR 3.
D4_TO_LEGACY_REQUIRE_TOKEN: dict[str, str] = {
    "cts.identity.gallery:review": "cts.identity.gallery_review",
    "face_calibration:review": "face_calibration.review",
    "visitors:review": "visitors.review",
    "persons.heights:read": "persons:heights_sync",
    "wearables:write": "wearables:manage",
    "wearables.teaching:write": "wearables:revoke_teaching",
    "wearables.site_config:read": "wearables:site_config",
}

# Pure ``:read`` router-twin tokens for MCP read tools (EG-M14 PR 3).
# Granted to ``mcp_readonly`` so OpenClaw Agent keeps calling all 53 read tools once
# MCP read tools adopt their router twins' D4 tokens. Note: ``get_face_calibration_summary``
# intentionally stays on ``mcp.tools:read`` because its HTTP twin shares the biometric-admin
# write token ``face_calibration:review``; ``mcp_readonly`` must never hold that token.
MCP_READONLY_TWIN_TOKENS: frozenset[str] = frozenset(
    {
        "activities:read",
        "conversations:read",
        "cts.analytics.heatmap:read",
        "cts.gait.trend:read",
        "cts.identity:read",
        "cts.keyframes:read",
        "cts.signals:read",
        "cts:read",
        "events:read",
        "guided_metrics:read",
        "guided_sessions:read",
        "identity_readiness:read",
        "image:read",
        "knowledge.documents:read",
        "media:read",
        "medication:read",
        "occupancy:read",
        "persons.location:read",
        "persons:read",
        "pipeline.meta:read",
        "quizzes:read",
        "rooms:read",
        "rules:read",
        "sensors:read",
        "signals.feed:read",
        "wearables:read",
        "workflows:read",
    }
)

# Exact (method, route_template) overrides for legacy overloaded tokens where
# distinct routes share one legacy name (e.g. ``admin``, ``caregiver``,
# ``cts.signals.view`` on POST /ack, ``cts.identity.view`` on POST /propose,
# ``cts.cameras.read`` roster vs. diagnostics, ``rules:write`` import/execute).
_EXACT_ROUTE_TOKENS: dict[tuple[str, str], str] = {
    # Legacy ``admin`` routes -> resource-scoped D4 tokens
    ("GET", "/api/v1/admin/config/current"): "admin.config:read",
    ("GET", "/api/v1/admin/telegram/trigger-defaults"): "admin.config:read",
    ("GET", "/api/v1/admin/notification-channels/audit"): "admin.channels:read",
    ("POST", "/api/v1/admin/config/reload"): "admin.config:write",
    ("GET", "/api/v1/media/buffer"): "media:read",
    ("GET", "/api/v1/media/aggregators"): "media:read",
    ("GET", "/api/v1/ha/entities"): "ha:read",
    ("GET", "/api/v1/ha/media-players"): "ha:read",
    ("POST", "/api/v1/ha/sync/rooms"): "ha:write",
    ("POST", "/api/v1/ha/sync/sensors"): "ha:write",
    ("GET", "/api/v1/image/fonts"): "image:read",
    ("GET", "/api/v1/image/states"): "image:read",
    ("POST", "/api/v1/image/preview"): "image:write",
    ("POST", "/api/v1/image/preview-form"): "image:write",
    ("POST", "/api/v1/image/render"): "image:write",
    ("POST", "/api/v1/image/reset"): "image:write",
    ("POST", "/api/v1/image/templates"): "image:write",
    ("PUT", "/api/v1/image/templates/{template_id}"): "image:write",
    ("PUT", "/api/v1/image/templates/{template_id}/image"): "image:write",
    ("DELETE", "/api/v1/image/templates/{template_id}"): "image:delete",
    ("POST", "/api/v1/persons"): "persons:write",
    ("PATCH", "/api/v1/persons/{person_id}"): "persons:write",
    ("DELETE", "/api/v1/persons/{person_id}"): "persons:delete",
    ("POST", "/api/v1/persons/{person_id}/enroll"): "persons.enrollment:write",
    ("DELETE", "/api/v1/persons/{person_id}/enrollment"): "persons.enrollment:delete",
    ("POST", "/api/v1/workflows/{execution_id}/cancel"): "workflows:execute",
    ("POST", "/api/v1/workflows/{execution_id}/rerun"): "workflows:execute",
    # Legacy ``caregiver`` routes -> resource-scoped D4 tokens
    ("GET", "/api/v1/activities"): "activities:read",
    ("GET", "/api/v1/activities/reports/{person_id}/{date}"): "activities:read",
    ("GET", "/api/v1/activities/reports/{person_id}/{date}/regenerate"): "activities:read",
    ("GET", "/api/v1/activities/sessions/open"): "activities:read",
    ("GET", "/api/v1/activities/timeline"): "activities:read",
    ("POST", "/api/v1/activities/sessions/open"): "activities.sessions:write",
    ("POST", "/api/v1/activities/sessions/{session_id}/close"): "activities.sessions:write",
    ("GET", "/api/v1/conversations/recent"): "conversations:read",
    ("GET", "/api/v1/occupancy/"): "occupancy:read",
    ("GET", "/api/v1/occupancy/history"): "occupancy:read",
    ("GET", "/api/v1/persons"): "persons:read",
    ("GET", "/api/v1/persons/enrolled"): "persons:read",
    ("GET", "/api/v1/persons/roster-health"): "persons:read",
    ("GET", "/api/v1/persons/{person_id}"): "persons:read",
    ("GET", "/api/v1/persons/{person_id}/enrollment"): "persons:read",
    ("GET", "/api/v1/persons/{person_id}/height-profile"): "persons:read",
    ("GET", "/api/v1/pipeline/ingest/activity"): "pipeline.runs:read",
    ("GET", "/api/v1/pipeline/runs"): "pipeline.runs:read",
    ("GET", "/api/v1/pipeline/runs/{execution_id}"): "pipeline.runs:read",
    ("GET", "/api/v1/signals/feed"): "signals.feed:read",
    ("GET", "/api/v1/workflows"): "workflows:read",
    ("GET", "/api/v1/workflows/{execution_id}"): "workflows:read",
    ("GET", "/api/v1/workflows/{execution_id}/detail"): "workflows:read",
    # Overloaded ``cts.signals.view`` writes
    ("POST", "/api/v1/cts/signals/{signal_id}/ack"): "cts.signals:acknowledge",
    ("POST", "/api/v1/cts/dashboard/suppressions"): "cts.signals.suppressions:write",
    ("DELETE", "/api/v1/cts/dashboard/suppressions/{suppression_id}"): (
        "cts.signals.suppressions:delete"
    ),
    # Overloaded ``cts.identity.view`` write
    ("POST", "/api/v1/cts/identity/corrections/propose"): "cts.identity:propose",
    # Overloaded ``cts.identity.correct`` reads/bboxes/corrections
    ("GET", "/api/v1/cts/identity/keyframes/{keyframe_id}/bboxes"): "cts.bboxes:read",
    ("PUT", "/api/v1/cts/identity/bboxes/{annotation_id}/override"): "cts.bboxes:write",
    ("POST", "/api/v1/cts/identity/corrections/apply"): "cts.identity.corrections:correct",
    ("POST", "/api/v1/cts/identity/corrections/{correction_id}/compensate"): (
        "cts.identity.corrections:correct"
    ),
    # Overloaded ``cts.cameras.read`` roster (cts_ingress least-privilege) vs. writes
    ("GET", "/api/v1/cts/cameras"): "cts.cameras.roster:read",
    ("GET", "/api/v1/cts/overlap_groups"): "cts.cameras.roster:read",
    ("GET", "/api/v1/cts/transit-zones"): "cts.cameras.roster:read",
    ("POST", "/api/v1/cts/cameras/optics-preview"): "cts.cameras:write",
    ("POST", "/api/v1/cts/cameras/test-connect"): "cts.cameras:write",
    # Overloaded ``cts.cameras.write`` transit zones (caregiver_admin granted explicitly)
    ("POST", "/api/v1/cts/transit-zones"): "cts.transit_zones:write",
    ("PATCH", "/api/v1/cts/transit-zones/{zone_id}"): "cts.transit_zones:write",
    ("DELETE", "/api/v1/cts/transit-zones/{zone_id}"): "cts.transit_zones:write",
    # Overloaded ``cts.calibrate`` read vs. mutate
    ("GET", "/api/v1/cts/calibration/floor_region_default/{camera_id}"): "cts.calibration:read",
    ("GET", "/api/v1/cts/calibration/homography/{camera_id}"): "cts.calibration:read",
    ("GET", "/api/v1/cts/calibration/privacy_zones/{camera_id}"): "cts.calibration:read",
    ("GET", "/api/v1/cts/calibration/visibility_polygons"): "cts.calibration:read",
    # Overloaded ``cts.keyframes.view`` write
    ("POST", "/api/v1/cts/keyframes/{sample_id}/retain"): "cts.keyframes:write",
    # Overloaded ``cts.presence.view`` reload
    ("POST", "/api/v1/cts/presence-config/reload"): "cts.presence.config:write",
    # Overloaded ``rules:read`` pipeline metadata vs. POST validation/preview
    ("GET", "/api/v1/pipeline/channel-types"): "pipeline.meta:read",
    ("GET", "/api/v1/pipeline/data-keys"): "pipeline.meta:read",
    ("GET", "/api/v1/pipeline/filter-types"): "pipeline.meta:read",
    ("GET", "/api/v1/pipeline/image-sources/sample"): "pipeline.meta:read",
    ("GET", "/api/v1/pipeline/llm-models"): "pipeline.meta:read",
    ("GET", "/api/v1/pipeline/step-types"): "pipeline.meta:read",
    ("POST", "/api/v1/pipeline/cron/preview"): "rules:write",
    ("POST", "/api/v1/rules/{rule_id}/validate"): "rules:write",
    # Overloaded ``rules:write`` import + execute (MCP parity)
    ("POST", "/api/v1/rules/import"): "rules:import",
    ("POST", "/api/v1/rules/import/preview"): "rules:import",
    ("POST", "/api/v1/rules/{rule_id}/execute"): "rules:execute",
}

# Direct legacy-token -> D4-token renames for non-overloaded tokens.
_DECLARED_TOKEN_RENAMES: dict[str, str] = {
    # Legacy METHOD /path tokens
    "GET /api/v1/info-cards": "info_cards:read",
    "POST /api/v1/info-cards": "info_cards:write",
    "PATCH /api/v1/info-cards": "info_cards:write",
    "DELETE /api/v1/info-cards": "info_cards:delete",
    "GET /api/v1/knowledge/documents": "knowledge.documents:read",
    "POST /api/v1/knowledge/documents": "knowledge.documents:write",
    "PATCH /api/v1/knowledge/documents": "knowledge.documents:write",
    "DELETE /api/v1/knowledge/documents": "knowledge.documents:delete",
    "GET /api/v1/knowledge/layouts": "knowledge.layouts:read",
    "GET /api/v1/knowledge-interactions": "knowledge.interactions:read",
    "GET /api/v1/quizzes": "quizzes:read",
    "POST /api/v1/quizzes": "quizzes:write",
    "PATCH /api/v1/quizzes": "quizzes:write",
    "DELETE /api/v1/quizzes": "quizzes:delete",
    "GET /api/v1/interactive-responses": "interactive_responses:read",
    # Legacy dotted tokens
    "cts.view": "cts:read",
    "cts.analytics.heatmap.view": "cts.analytics.heatmap:read",
    "cts.bboxes.write": "cts.bboxes:write",
    "cts.calibrate": "cts.calibration:calibrate",
    "cts.calibration.view": "cts.calibration:read",
    "cts.cameras.read": "cts.cameras:read",
    "cts.cameras.write": "cts.cameras:write",
    "cts.gait.trend.view": "cts.gait.trend:read",
    "cts.identity.correct": "cts.identity:correct",
    "cts.identity.gallery_review": "cts.identity.gallery:review",
    "cts.identity.view": "cts.identity:read",
    "cts.keyframes.view": "cts.keyframes:read",
    "cts.presence.view": "cts.presence:read",
    "cts.reports.weekly.view": "cts.reports.weekly:read",
    "cts.signals.delete": "cts.signals:delete",
    "cts.signals.evidence.view": "cts.signals.evidence:read",
    "cts.signals.view": "cts.signals:read",
    "face_calibration.review": "face_calibration:review",
    "persons.read": "persons.location:read",
    "persons.write_overrides": "persons.location:write",
    "visitors.review": "visitors:review",
    # Post-2026-10-21 non-D4 action tokens (normalized per EG-M14 A2)
    "device:recamera": "device.recamera:ingest",
    "persons:heights_sync": "persons.heights:read",
    "wearables:manage": "wearables:write",
    "wearables:revoke_teaching": "wearables.teaching:write",
    "wearables:site_config": "wearables.site_config:read",
}


def resolve_proposed_token(method: str, route_template: str, declared_token: str) -> str:
    """Resolve the target D4 token for a route given its current declaration.

    Raises :class:`ValueError` if the resolved token fails :func:`is_valid_d4_token`,
    so an unmapped legacy token fails loudly instead of leaking through.
    """
    key = (method.upper(), route_template)
    if key in _EXACT_ROUTE_TOKENS:
        resolved = _EXACT_ROUTE_TOKENS[key]
    elif declared_token in _DECLARED_TOKEN_RENAMES:
        resolved = _DECLARED_TOKEN_RENAMES[declared_token]
    else:
        resolved = declared_token

    if not is_valid_d4_token(resolved):
        raise ValueError(
            f"Route {method.upper()} {route_template} (declared {declared_token!r}) "
            f"resolved to non-D4 token {resolved!r}"
        )
    return resolved


@dataclass(frozen=True)
class ApprovalDelta:
    """Expected cell delta between today's globs and the proposed D4 ``roles:`` map."""

    role: str
    method: str
    path: str
    token: str
    today: bool
    proposed: bool
    reason: str
    recommendation: str


# Table A: unavoidable cell deltas caused by grouping sibling routes under one D4 token.
# Every entry here must be explicitly reviewed in M14-T before PR 3 switches enforcement.
M14T_CONSOLIDATION_DELTAS: tuple[ApprovalDelta, ...] = (
    ApprovalDelta(
        role="caregiver",
        method="PUT",
        path="/api/v1/info-cards/{card_id}/slots/{slot_index}",
        token="info_cards:write",
        today=False,
        proposed=True,
        reason=(
            "Caregiver already holds POST/PATCH/DELETE on /api/v1/info-cards*; "
            "PUT was omitted from the legacy globs despite declaring POST /api/v1/info-cards."
        ),
        recommendation="Approve: align slot image upload with existing caregiver info-card writes.",
    ),
    ApprovalDelta(
        role="caregiver",
        method="PUT",
        path="/api/v1/quizzes/{quiz_id}/questions/{qid}/image",
        token="quizzes:write",
        today=False,
        proposed=True,
        reason=(
            "Caregiver already holds POST/PATCH/DELETE on /api/v1/quizzes*; "
            "PUT was omitted from the legacy globs despite declaring POST /api/v1/quizzes."
        ),
        recommendation="Approve: align quiz question image upload with existing caregiver quiz writes.",
    ),
    ApprovalDelta(
        role="cts_ingress",
        method="GET",
        path="/api/v1/rooms/{room_id}/occupants",
        token="persons.location:read",
        today=True,
        proposed=False,
        reason=(
            "Legacy GET /api/v1/rooms* glob accidentally matched /rooms/{id}/occupants; "
            "rtsp-ingress only reads room geometry and camera rosters."
        ),
        recommendation="Approve: revoke incidental occupant-tracking read from rtsp-ingress.",
    ),
    ApprovalDelta(
        role="cts_ingress",
        method="GET",
        path="/api/v1/rooms/{room_id}/zones",
        token="room_zones:read",
        today=True,
        proposed=False,
        reason=(
            "Legacy GET /api/v1/rooms* glob accidentally matched /rooms/{id}/zones; "
            "rtsp-ingress only needs /api/v1/rooms* room list and floor plan."
        ),
        recommendation="Approve: revoke incidental room-zones read from rtsp-ingress.",
    ),
)

# Table B: zero-delta review items surfaced from today's coarse globs and inert grants.
# Proposed ``roles:`` reproduces today's exact reach for all of these during shadow soak;
# the owner decides per item whether to tighten/grant before PR 3.
M14T_RECOMMENDED_REVIEW_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "caregiver, caregiver_admin",
        "admin:read, admin.config:read, admin.channels:read, media:read",
        "ALLOW (via GET /api/v1/*)",
        "Review: decide whether caregiver should keep read-only health/config/media diagnostics or drop admin.config:read / admin.channels:read before PR 3.",
    ),
    (
        "caregiver_admin",
        "cts.cameras:write, cts.calibration:calibrate, cts.signals:delete, cts.identity:correct",
        "DENY (listed in permission_map as inert non-glob tokens)",
        "Review: permission_map lists these tokens on caregiver_admin, but glob mode never honored them. Keep DENY during shadow; explicitly approve if caregiver_admin should gain write/calibrate/delete access in PR 3.",
    ),
    (
        "caregiver, caregiver_admin",
        "gate_graphs:write, guided_sessions:takeover, medication:write, room_zones:write, routines:write",
        "DENY (listed in permission_map as inert non-glob tokens)",
        "Review: caregiver/caregiver_admin list these D4 tokens in permission_map, but glob mode never expanded nested keys recursively so POST/PATCH/DELETE are currently denied. Decide whether to grant before PR 3.",
    ),
    (
        "device_reterminal",
        "image:read (GET /api/v1/image/fonts, /states, /templates*)",
        "ALLOW (via GET /api/v1/image/*)",
        "Review: reTerminal hardware only polls GET /api/v1/image/active; consider narrowing to image.active:read after shadow confirms zero traffic to fonts/states/templates.",
    ),
    (
        "caregiver",
        "cts.presence.config:write (POST /api/v1/cts/presence-config/reload)",
        "ALLOW (explicit caregiver glob; caregiver_admin lacks it)",
        "Review: caregiver can reload presence config while caregiver_admin cannot; verify intended asymmetry.",
    ),
)
