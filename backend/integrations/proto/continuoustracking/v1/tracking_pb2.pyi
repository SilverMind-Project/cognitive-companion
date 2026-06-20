from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PresenceEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRESENCE_EVENT_TYPE_UNSPECIFIED: _ClassVar[PresenceEventType]
    PRESENCE_EVENT_TYPE_APPEARED: _ClassVar[PresenceEventType]
    PRESENCE_EVENT_TYPE_DISAPPEARED: _ClassVar[PresenceEventType]

class DwellEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DWELL_EVENT_TYPE_UNSPECIFIED: _ClassVar[DwellEventType]
    DWELL_EVENT_TYPE_STARTED: _ClassVar[DwellEventType]
    DWELL_EVENT_TYPE_ENDED: _ClassVar[DwellEventType]

class SceneSampleKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SCENE_SAMPLE_KIND_UNSPECIFIED: _ClassVar[SceneSampleKind]
    SCENE_SAMPLE_KIND_ISOLATED_PERSON: _ClassVar[SceneSampleKind]
    SCENE_SAMPLE_KIND_INTERACTION: _ClassVar[SceneSampleKind]
    SCENE_SAMPLE_KIND_CROWD: _ClassVar[SceneSampleKind]
    SCENE_SAMPLE_KIND_EMPTY: _ClassVar[SceneSampleKind]
PRESENCE_EVENT_TYPE_UNSPECIFIED: PresenceEventType
PRESENCE_EVENT_TYPE_APPEARED: PresenceEventType
PRESENCE_EVENT_TYPE_DISAPPEARED: PresenceEventType
DWELL_EVENT_TYPE_UNSPECIFIED: DwellEventType
DWELL_EVENT_TYPE_STARTED: DwellEventType
DWELL_EVENT_TYPE_ENDED: DwellEventType
SCENE_SAMPLE_KIND_UNSPECIFIED: SceneSampleKind
SCENE_SAMPLE_KIND_ISOLATED_PERSON: SceneSampleKind
SCENE_SAMPLE_KIND_INTERACTION: SceneSampleKind
SCENE_SAMPLE_KIND_CROWD: SceneSampleKind
SCENE_SAMPLE_KIND_EMPTY: SceneSampleKind

class TrackingEvent(_message.Message):
    __slots__ = ("camera_id", "event_time_unix_ns", "frame_ref", "detections", "identity_revisions", "room_name", "event_id", "identity_snapshots")
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    FRAME_REF_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_REVISIONS_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_SNAPSHOTS_FIELD_NUMBER: _ClassVar[int]
    camera_id: str
    event_time_unix_ns: int
    frame_ref: FrameRef
    detections: _containers.RepeatedCompositeFieldContainer[Detection]
    identity_revisions: _containers.RepeatedCompositeFieldContainer[IdentityRevision]
    room_name: str
    event_id: str
    identity_snapshots: _containers.RepeatedCompositeFieldContainer[IdentitySnapshot]
    def __init__(self, camera_id: _Optional[str] = ..., event_time_unix_ns: _Optional[int] = ..., frame_ref: _Optional[_Union[FrameRef, _Mapping]] = ..., detections: _Optional[_Iterable[_Union[Detection, _Mapping]]] = ..., identity_revisions: _Optional[_Iterable[_Union[IdentityRevision, _Mapping]]] = ..., room_name: _Optional[str] = ..., event_id: _Optional[str] = ..., identity_snapshots: _Optional[_Iterable[_Union[IdentitySnapshot, _Mapping]]] = ...) -> None: ...

class FrameRef(_message.Message):
    __slots__ = ("minio_key", "width", "height", "frame_index", "capture_time_unix_ns")
    MINIO_KEY_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    FRAME_INDEX_FIELD_NUMBER: _ClassVar[int]
    CAPTURE_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    minio_key: str
    width: int
    height: int
    frame_index: int
    capture_time_unix_ns: int
    def __init__(self, minio_key: _Optional[str] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., frame_index: _Optional[int] = ..., capture_time_unix_ns: _Optional[int] = ...) -> None: ...

class Detection(_message.Message):
    __slots__ = ("detection_id", "bbox", "embedding", "confidence", "floor_point", "pose_keypoints", "trail", "evidence", "floor_x", "floor_y", "posture", "ph_id")
    DETECTION_ID_FIELD_NUMBER: _ClassVar[int]
    BBOX_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    FLOOR_POINT_FIELD_NUMBER: _ClassVar[int]
    POSE_KEYPOINTS_FIELD_NUMBER: _ClassVar[int]
    TRAIL_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    FLOOR_X_FIELD_NUMBER: _ClassVar[int]
    FLOOR_Y_FIELD_NUMBER: _ClassVar[int]
    POSTURE_FIELD_NUMBER: _ClassVar[int]
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    detection_id: str
    bbox: BoundingBox
    embedding: _containers.RepeatedScalarFieldContainer[float]
    confidence: float
    floor_point: FloorPoint
    pose_keypoints: _containers.RepeatedCompositeFieldContainer[PoseKeypoint]
    trail: _containers.RepeatedCompositeFieldContainer[TrailPoint]
    evidence: PosteriorEvidence
    floor_x: float
    floor_y: float
    posture: str
    ph_id: str
    def __init__(self, detection_id: _Optional[str] = ..., bbox: _Optional[_Union[BoundingBox, _Mapping]] = ..., embedding: _Optional[_Iterable[float]] = ..., confidence: _Optional[float] = ..., floor_point: _Optional[_Union[FloorPoint, _Mapping]] = ..., pose_keypoints: _Optional[_Iterable[_Union[PoseKeypoint, _Mapping]]] = ..., trail: _Optional[_Iterable[_Union[TrailPoint, _Mapping]]] = ..., evidence: _Optional[_Union[PosteriorEvidence, _Mapping]] = ..., floor_x: _Optional[float] = ..., floor_y: _Optional[float] = ..., posture: _Optional[str] = ..., ph_id: _Optional[str] = ...) -> None: ...

class PoseKeypoint(_message.Message):
    __slots__ = ("x", "y", "score")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    score: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., score: _Optional[float] = ...) -> None: ...

class TrailPoint(_message.Message):
    __slots__ = ("x", "y")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...

class PosteriorEvidence(_message.Message):
    __slots__ = ("top_prob", "top2_prob", "face_anchor_used")
    TOP_PROB_FIELD_NUMBER: _ClassVar[int]
    TOP2_PROB_FIELD_NUMBER: _ClassVar[int]
    FACE_ANCHOR_USED_FIELD_NUMBER: _ClassVar[int]
    top_prob: float
    top2_prob: float
    face_anchor_used: bool
    def __init__(self, top_prob: _Optional[float] = ..., top2_prob: _Optional[float] = ..., face_anchor_used: bool = ...) -> None: ...

class BoundingBox(_message.Message):
    __slots__ = ("x_min", "y_min", "x_max", "y_max")
    X_MIN_FIELD_NUMBER: _ClassVar[int]
    Y_MIN_FIELD_NUMBER: _ClassVar[int]
    X_MAX_FIELD_NUMBER: _ClassVar[int]
    Y_MAX_FIELD_NUMBER: _ClassVar[int]
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    def __init__(self, x_min: _Optional[int] = ..., y_min: _Optional[int] = ..., x_max: _Optional[int] = ..., y_max: _Optional[int] = ...) -> None: ...

class FloorPoint(_message.Message):
    __slots__ = ("x_mm", "y_mm", "calibrated")
    X_MM_FIELD_NUMBER: _ClassVar[int]
    Y_MM_FIELD_NUMBER: _ClassVar[int]
    CALIBRATED_FIELD_NUMBER: _ClassVar[int]
    x_mm: int
    y_mm: int
    calibrated: bool
    def __init__(self, x_mm: _Optional[int] = ..., y_mm: _Optional[int] = ..., calibrated: bool = ...) -> None: ...

class IdentityRevision(_message.Message):
    __slots__ = ("ph_id", "candidates", "map_identity_id", "posterior_entropy", "revision_time_unix_ns", "revision_id", "previous_identity_id", "new_identity_id", "reason", "evidence_json", "inferred_identity_id", "effective_identity_id", "authority", "decision_source", "decision_id", "conflict", "revision_kind", "range_start_unix_ns", "range_end_unix_ns", "range_authority", "revision_range_id", "correction_id", "required_projections", "revision_schema_version")
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    CANDIDATES_FIELD_NUMBER: _ClassVar[int]
    MAP_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    POSTERIOR_ENTROPY_FIELD_NUMBER: _ClassVar[int]
    REVISION_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    REVISION_ID_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    NEW_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_JSON_FIELD_NUMBER: _ClassVar[int]
    INFERRED_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    EFFECTIVE_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    AUTHORITY_FIELD_NUMBER: _ClassVar[int]
    DECISION_SOURCE_FIELD_NUMBER: _ClassVar[int]
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    CONFLICT_FIELD_NUMBER: _ClassVar[int]
    REVISION_KIND_FIELD_NUMBER: _ClassVar[int]
    RANGE_START_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    RANGE_AUTHORITY_FIELD_NUMBER: _ClassVar[int]
    REVISION_RANGE_ID_FIELD_NUMBER: _ClassVar[int]
    CORRECTION_ID_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_PROJECTIONS_FIELD_NUMBER: _ClassVar[int]
    REVISION_SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    ph_id: str
    candidates: _containers.RepeatedCompositeFieldContainer[IdentityCandidate]
    map_identity_id: str
    posterior_entropy: float
    revision_time_unix_ns: int
    revision_id: str
    previous_identity_id: str
    new_identity_id: str
    reason: str
    evidence_json: str
    inferred_identity_id: str
    effective_identity_id: str
    authority: str
    decision_source: str
    decision_id: str
    conflict: str
    revision_kind: str
    range_start_unix_ns: int
    range_end_unix_ns: int
    range_authority: str
    revision_range_id: str
    correction_id: str
    required_projections: _containers.RepeatedScalarFieldContainer[str]
    revision_schema_version: str
    def __init__(self, ph_id: _Optional[str] = ..., candidates: _Optional[_Iterable[_Union[IdentityCandidate, _Mapping]]] = ..., map_identity_id: _Optional[str] = ..., posterior_entropy: _Optional[float] = ..., revision_time_unix_ns: _Optional[int] = ..., revision_id: _Optional[str] = ..., previous_identity_id: _Optional[str] = ..., new_identity_id: _Optional[str] = ..., reason: _Optional[str] = ..., evidence_json: _Optional[str] = ..., inferred_identity_id: _Optional[str] = ..., effective_identity_id: _Optional[str] = ..., authority: _Optional[str] = ..., decision_source: _Optional[str] = ..., decision_id: _Optional[str] = ..., conflict: _Optional[str] = ..., revision_kind: _Optional[str] = ..., range_start_unix_ns: _Optional[int] = ..., range_end_unix_ns: _Optional[int] = ..., range_authority: _Optional[str] = ..., revision_range_id: _Optional[str] = ..., correction_id: _Optional[str] = ..., required_projections: _Optional[_Iterable[str]] = ..., revision_schema_version: _Optional[str] = ...) -> None: ...

class IdentitySnapshot(_message.Message):
    __slots__ = ("ph_id", "identity_id", "top_probability", "second_probability", "posterior_entropy", "direct_face_evidence", "evidence_json", "mean_quality", "inferred_identity_id", "effective_identity_id", "authority", "decision_source", "decision_id", "conflict", "last_independent_evidence_at_unix_ns", "config_hash", "model_set_version")
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    TOP_PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    SECOND_PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    POSTERIOR_ENTROPY_FIELD_NUMBER: _ClassVar[int]
    DIRECT_FACE_EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_JSON_FIELD_NUMBER: _ClassVar[int]
    MEAN_QUALITY_FIELD_NUMBER: _ClassVar[int]
    INFERRED_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    EFFECTIVE_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    AUTHORITY_FIELD_NUMBER: _ClassVar[int]
    DECISION_SOURCE_FIELD_NUMBER: _ClassVar[int]
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    CONFLICT_FIELD_NUMBER: _ClassVar[int]
    LAST_INDEPENDENT_EVIDENCE_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    CONFIG_HASH_FIELD_NUMBER: _ClassVar[int]
    MODEL_SET_VERSION_FIELD_NUMBER: _ClassVar[int]
    ph_id: str
    identity_id: str
    top_probability: float
    second_probability: float
    posterior_entropy: float
    direct_face_evidence: bool
    evidence_json: str
    mean_quality: float
    inferred_identity_id: str
    effective_identity_id: str
    authority: str
    decision_source: str
    decision_id: str
    conflict: str
    last_independent_evidence_at_unix_ns: int
    config_hash: str
    model_set_version: str
    def __init__(self, ph_id: _Optional[str] = ..., identity_id: _Optional[str] = ..., top_probability: _Optional[float] = ..., second_probability: _Optional[float] = ..., posterior_entropy: _Optional[float] = ..., direct_face_evidence: bool = ..., evidence_json: _Optional[str] = ..., mean_quality: _Optional[float] = ..., inferred_identity_id: _Optional[str] = ..., effective_identity_id: _Optional[str] = ..., authority: _Optional[str] = ..., decision_source: _Optional[str] = ..., decision_id: _Optional[str] = ..., conflict: _Optional[str] = ..., last_independent_evidence_at_unix_ns: _Optional[int] = ..., config_hash: _Optional[str] = ..., model_set_version: _Optional[str] = ...) -> None: ...

class IdentityCandidate(_message.Message):
    __slots__ = ("identity_id", "display_name", "probability")
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    identity_id: str
    display_name: str
    probability: float
    def __init__(self, identity_id: _Optional[str] = ..., display_name: _Optional[str] = ..., probability: _Optional[float] = ...) -> None: ...

class PresenceEvent(_message.Message):
    __slots__ = ("ph_id", "identity_id", "event_type", "room_name", "event_time_unix_ns")
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    ph_id: str
    identity_id: str
    event_type: PresenceEventType
    room_name: str
    event_time_unix_ns: int
    def __init__(self, ph_id: _Optional[str] = ..., identity_id: _Optional[str] = ..., event_type: _Optional[_Union[PresenceEventType, str]] = ..., room_name: _Optional[str] = ..., event_time_unix_ns: _Optional[int] = ...) -> None: ...

class DwellEvent(_message.Message):
    __slots__ = ("ph_id", "identity_id", "event_type", "room_name", "event_time_unix_ns", "duration_s")
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    DURATION_S_FIELD_NUMBER: _ClassVar[int]
    ph_id: str
    identity_id: str
    event_type: DwellEventType
    room_name: str
    event_time_unix_ns: int
    duration_s: int
    def __init__(self, ph_id: _Optional[str] = ..., identity_id: _Optional[str] = ..., event_type: _Optional[_Union[DwellEventType, str]] = ..., room_name: _Optional[str] = ..., event_time_unix_ns: _Optional[int] = ..., duration_s: _Optional[int] = ...) -> None: ...

class CCIdentityAssertion(_message.Message):
    __slots__ = ("person_id", "camera_id", "captured_at_unix_ns", "floor_x_m", "floor_y_m", "raw_similarity", "calibrated_confidence", "calibration_status", "source", "model_version", "preprocessing_version")
    PERSON_ID_FIELD_NUMBER: _ClassVar[int]
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    CAPTURED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    FLOOR_X_M_FIELD_NUMBER: _ClassVar[int]
    FLOOR_Y_M_FIELD_NUMBER: _ClassVar[int]
    RAW_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    CALIBRATED_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    CALIBRATION_STATUS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    PREPROCESSING_VERSION_FIELD_NUMBER: _ClassVar[int]
    person_id: str
    camera_id: str
    captured_at_unix_ns: int
    floor_x_m: float
    floor_y_m: float
    raw_similarity: float
    calibrated_confidence: float
    calibration_status: str
    source: str
    model_version: str
    preprocessing_version: str
    def __init__(self, person_id: _Optional[str] = ..., camera_id: _Optional[str] = ..., captured_at_unix_ns: _Optional[int] = ..., floor_x_m: _Optional[float] = ..., floor_y_m: _Optional[float] = ..., raw_similarity: _Optional[float] = ..., calibrated_confidence: _Optional[float] = ..., calibration_status: _Optional[str] = ..., source: _Optional[str] = ..., model_version: _Optional[str] = ..., preprocessing_version: _Optional[str] = ...) -> None: ...
