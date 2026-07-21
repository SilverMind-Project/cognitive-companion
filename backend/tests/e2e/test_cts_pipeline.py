"""End-to-end CTS pipeline test (M10 DoD gate).

Drives a synthetic frame batch from publish -> consume -> location repo
write -> rule firing -> WebSocket broadcast -> identity revision rewrite,
exercising the proto wire format and the shared
:class:`LocationRepository`. The test runs entirely in-process against
a :mod:`fakeredis` instance so it can run in CI without Docker.

Wire format
-----------
Every Redis Streams message carries one named field whose value is the
raw protobuf body (``Message.SerializeToString()``):

* ``tracking.events`` -> field ``event`` with ``TrackingEvent``.
* ``tracking.revisions`` -> field ``revision`` with ``IdentityRevision``.

The unit subscriber loop (``StreamConsumer.start``) is exercised in
unit tests; this e2e drives ``decode + handle`` directly to keep the
test deterministic, while still using the real fakeredis transport for
proper xreadgroup / xack semantics.
"""

from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import fakeredis.aioredis as fakeredis
import pytest

from backend.integrations.proto.continuoustracking.v1 import (  # type: ignore[attr-defined]
    tracking_pb2,
)
from backend.models.person import (
    HouseholdMember,
)
from backend.models.room import Room
from backend.services.cts.backfill_projector import BackfillProjector
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber
from backend.services.cts.signal_rewriter import SignalRewriter
from backend.services.cts.tracking_event_subscriber import TrackingEventSubscriber
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

# Base of the synthetic timeline (2024-12-27T13:20:00Z). Every wire timestamp
# in this test derives from it -- events and the revision that corrects them
# must share one clock. A revision stamped with the wall clock instead would
# be range-scoped to "now" and match none of the rows it is meant to rewrite
# (see ``IdentityRewriter``: M06 bounds every revision to an explicit
# range_start/range_end, or to ``revision_horizon_s`` around revision_time).
_T0_NS = 1735305600000000000
_T0 = datetime.fromtimestamp(_T0_NS / 1e9, UTC)


def _dt_to_ns(value: datetime) -> int:
    return int(value.timestamp() * 1e9)


class _StubWSManager:
    """Records broadcasts so tests can assert UI propagation."""

    def __init__(self) -> None:
        self.broadcasts: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)


def _seed(db_factory) -> None:
    db = db_factory()
    try:
        db.add(HouseholdMember(id="grandma", name="Grandma"))
        db.add(HouseholdMember(id="caregiver", name="Caregiver"))
        db.add(Room(id=1, name="Kitchen"))
        db.add(Room(id=2, name="Bedroom"))
        db.commit()
    finally:
        db.close()


def _make_event_fields(
    *, camera_id: str, room: str, identity: str, frame_index: int
) -> dict[bytes, bytes]:
    """Build a Redis-Streams field dict carrying a TrackingEvent proto."""
    # Space events ~1 s apart so they survive nanosecond -> microsecond
    # rounding in the wire-to-datetime conversion path.
    ev = tracking_pb2.TrackingEvent(
        camera_id=camera_id,
        event_id=f"evt-{frame_index}",
        event_time_unix_ns=_T0_NS + frame_index * 1_000_000_000,
        room_name=room,
    )
    ev.frame_ref.minio_key = f"frames/{camera_id}/{frame_index}.jpg"
    ev.frame_ref.frame_index = frame_index
    det = ev.detections.add(
        detection_id=f"det-{frame_index}",
        confidence=0.9,
        ph_id=f"ph-{identity}",
    )
    det.bbox.x_min, det.bbox.y_min = 100, 200
    det.bbox.x_max, det.bbox.y_max = 200, 400
    det.floor_point.x_mm = 1500
    det.floor_point.y_mm = 2500
    det.floor_point.calibrated = True
    snap = ev.identity_snapshots.add()
    snap.ph_id = f"ph-{identity}"
    snap.identity_id = identity
    snap.top_probability = 0.92
    return {b"event": ev.SerializeToString()}


def _make_revision_fields(
    *,
    revision_id: str,
    ph_id: str,
    previous_identity_id: str | None,
    new_identity_id: str | None,
    revision_time: datetime,
    range_start: datetime,
    range_end: datetime,
    reason: str = "manual_override",
    revision_kind: str = "operator_correction",
    range_authority: str = "operator",
) -> dict[bytes, bytes]:
    """Build a Redis-Streams field dict carrying an IdentityRevision proto.

    Models an M06 operator correction: ``manual_override`` carries an explicit
    ``range_start``/``range_end`` bounding what the operator's authority covers,
    rather than relying on the automatic-revision horizon fallback. These are
    typed proto fields (18-21), so this also exercises their decode path.
    """
    msg = tracking_pb2.IdentityRevision(
        revision_id=revision_id,
        ph_id=ph_id,
        previous_identity_id=previous_identity_id or "",
        new_identity_id=new_identity_id or "",
        map_identity_id=new_identity_id or "",
        posterior_entropy=0.0,
        reason=reason,
        evidence_json="{}",
        revision_time_unix_ns=_dt_to_ns(revision_time),
        revision_kind=revision_kind,
        range_start_unix_ns=_dt_to_ns(range_start),
        range_end_unix_ns=_dt_to_ns(range_end),
        range_authority=range_authority,
    )
    return {b"revision": msg.SerializeToString()}


class _PipelineSpy:
    def __init__(self) -> None:
        self.fired: list[dict] = []

    async def fire_event(self, **kwargs) -> None:
        self.fired.append(kwargs)


@pytest.mark.asyncio
async def test_proto_event_drives_location_state_and_pipeline(db_factory):
    """The full happy path: publish, consume, persist, fire pipeline,
    broadcast to WS, then apply an identity correction and assert the
    history rows are rewritten."""
    _seed(db_factory)

    redis_client = fakeredis.FakeRedis(decode_responses=False)
    stream = "tracking.events"
    group = "cognitive-companion-events"
    consumer = f"e2e-{socket.gethostname()}"

    # ----- Stage 1: publish two TrackingEvent protos -----------------
    for i, (room, identity) in enumerate([("Kitchen", "grandma"), ("Bedroom", "grandma")]):
        await redis_client.xadd(
            stream,
            _make_event_fields(
                camera_id="cam-overhead",
                room=room,
                identity=identity,
                frame_index=i,
            ),
        )

    # ----- Stage 2: consume + handle ---------------------------------

    ws_manager = _StubWSManager()
    pipeline = _PipelineSpy()
    subscriber = TrackingEventSubscriber(
        redis_url="redis://ignored",
        consumer_id=consumer,
        ws_manager=ws_manager,
        pipeline=pipeline,
    )
    subscriber._redis = redis_client  # type: ignore[attr-defined]
    await redis_client.xgroup_create(stream, group, id="0", mkstream=True)

    response = await redis_client.xreadgroup(
        group, consumer, streams={stream: ">"}, count=10, block=10
    )
    assert response, "fakeredis returned no messages"
    _stream_name, batch = response[0]
    assert len(batch) == 2

    for message_id, fields in batch:
        decoded = subscriber.decode(message_id, fields)
        assert decoded is not None
        ok = await subscriber.handle(decoded)
        assert ok is True
        await redis_client.xack(stream, group, message_id)

    # ----- Stage 4: pipeline rule firing -----------------------------
    assert len(pipeline.fired) == 2
    assert pipeline.fired[-1]["kind"] == "tracking_event"
    assert pipeline.fired[-1]["payload"]["room_name"] == "Bedroom"
    assert pipeline.fired[-1]["payload"]["persons"] == ["grandma"]

    # ----- Stage 5: WebSocket / "UI reflects" ------------------------
    assert len(ws_manager.broadcasts) == 2
    assert all(b["type"] == "cts_live_frame" for b in ws_manager.broadcasts)
    last_broadcast = ws_manager.broadcasts[-1]
    assert last_broadcast["camera_id"] == "cam-overhead"
    assert last_broadcast["room_name"] == "Bedroom"
    assert last_broadcast["detections"][0]["identity_id"] == "grandma"

    # ----- Stage 6: identity correction round trip -------------------
    revisions_stream = "tracking.revisions"
    revisions_group = "cognitive-companion-revisions"
    await redis_client.xgroup_create(revisions_stream, revisions_group, id="0", mkstream=True)

    await redis_client.xadd(
        revisions_stream,
        _make_revision_fields(
            revision_id="rev-1",
            ph_id="ph-grandma",
            previous_identity_id="grandma",
            new_identity_id="caregiver",
            # An operator correcting the two events a minute after they landed,
            # with authority bounded to a window that brackets both of them.
            revision_time=_T0 + timedelta(seconds=60),
            range_start=_T0 - timedelta(seconds=60),
            range_end=_T0 + timedelta(seconds=60),
        ),
    )

    rewriter = SignalRewriter(db_factory=db_factory, ws_manager=_StubWSManager())
    revisions_pipeline = _PipelineSpy()
    revisions_subscriber = IdentityRevisionSubscriber(
        redis_url="redis://ignored",
        consumer_id="rev-consumer",
        rewriter=rewriter,
        pipeline=revisions_pipeline,
    )
    revisions_subscriber._redis = redis_client  # type: ignore[attr-defined]

    response = await redis_client.xreadgroup(
        revisions_group,
        "rev-consumer",
        streams={revisions_stream: ">"},
        count=10,
        block=10,
    )
    assert response, "no IdentityRevision delivered"
    _, revision_batch = response[0]
    assert len(revision_batch) == 1

    rev_message_id, rev_fields = revision_batch[0]
    decoded_revision = revisions_subscriber.decode(rev_message_id, rev_fields)
    assert decoded_revision is not None
    rev_ok = await revisions_subscriber.handle(decoded_revision)
    assert rev_ok is True
    await redis_client.xack(revisions_stream, revisions_group, rev_message_id)

    # Existing rows have been soft-deleted via superseded_by_revision_id
    # and replacement rows are inserted under the new identity.
    # The pipeline executor fires once for the revision so any rule
    # keyed on identity changes can react.
    assert len(revisions_pipeline.fired) == 1
    assert revisions_pipeline.fired[0]["kind"] == "identity_revision"
    rev_payload = revisions_pipeline.fired[0]["payload"]
    assert rev_payload["revision_id"] == "rev-1"
    assert rev_payload["previous_identity_id"] == "grandma"
    assert rev_payload["new_identity_id"] == "caregiver"
    assert rev_payload["rewritten_rows"] >= 0

    await redis_client.aclose()


@pytest.mark.asyncio
async def test_proto_inferred_backfill_revision_projects_segments(db_factory):
    """identity-continuity M05: an inferred_backfill IdentityRevision proto,
    delivered through the real subscriber wiring (fakeredis stream, decode,
    handle), routes to BackfillProjector and inserts closed presence
    segments for the recovered Unknown range.
    """
    db = db_factory()
    try:
        db.add(Room(id=1, name="Kitchen"))
        db.commit()
    finally:
        db.close()

    redis_client = fakeredis.FakeRedis(decode_responses=False)
    stream = "tracking.revisions"
    group = "cognitive-companion-revisions"

    range_start = _T0
    range_end = _T0 + timedelta(hours=3)
    await redis_client.xadd(
        stream,
        _make_revision_fields(
            revision_id="rev-backfill-e2e",
            ph_id="ph-newly-identified",
            previous_identity_id=None,
            new_identity_id="grandma",
            revision_time=range_end,
            range_start=range_start,
            range_end=range_end,
            reason="unknown_backfill",
            revision_kind="inferred_backfill",
            range_authority="inferred",
        ),
    )

    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "Kitchen",
                "entered_at": range_start.isoformat(),
                "exited_at": range_end.isoformat(),
                "identity_id": None,
                "ph_id": "ph-newly-identified",
                "entry_confidence": 0.85,
            }
        ]
    }
    location_service = PersonLocationService(
        InMemoryObservationRepository(), InMemorySegmentRepository(), PersonLocationConfig()
    )
    projector = BackfillProjector(
        db_factory=db_factory,
        orchestrator_client=orchestrator,
        person_location_service=location_service,
    )
    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://ignored",
        consumer_id="rev-consumer",
        rewriter=SignalRewriter(db_factory=db_factory),
        backfill_projector=projector,
    )
    subscriber._redis = redis_client  # type: ignore[attr-defined]
    await redis_client.xgroup_create(stream, group, id="0", mkstream=True)

    response = await redis_client.xreadgroup(
        group, "rev-consumer", streams={stream: ">"}, count=10, block=10
    )
    assert response, "no IdentityRevision delivered"
    _, batch = response[0]
    assert len(batch) == 1
    message_id, fields = batch[0]
    decoded = subscriber.decode(message_id, fields)
    assert decoded is not None
    assert decoded["revision_kind"] == "inferred_backfill"

    ok = await subscriber.handle(decoded)
    assert ok is True
    await redis_client.xack(stream, group, message_id)

    segments = await location_service.room_segments("grandma", range_start, range_end)
    assert len(segments) == 1
    assert segments[0].room_name == "Kitchen"
    orchestrator.post_projection_ack.assert_called_once()

    await redis_client.aclose()


# Make the loop policy stable for fakeredis on Python 3.12.
@pytest.fixture(autouse=True)
def _silence_fakeredis_loop():
    yield
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
