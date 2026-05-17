from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TrackingEvent(_message.Message):
    __slots__ = ("camera_id", "event_time_unix_ns", "frame_ref", "detections", "identity_revisions", "room_name", "event_id")
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    FRAME_REF_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_REVISIONS_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    camera_id: str
    event_time_unix_ns: int
    frame_ref: FrameRef
    detections: _containers.RepeatedCompositeFieldContainer[Detection]
    identity_revisions: _containers.RepeatedCompositeFieldContainer[IdentityRevision]
    room_name: str
    event_id: str
    def __init__(self, camera_id: _Optional[str] = ..., event_time_unix_ns: _Optional[int] = ..., frame_ref: _Optional[_Union[FrameRef, _Mapping]] = ..., detections: _Optional[_Iterable[_Union[Detection, _Mapping]]] = ..., identity_revisions: _Optional[_Iterable[_Union[IdentityRevision, _Mapping]]] = ..., room_name: _Optional[str] = ..., event_id: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("detection_id", "bbox", "embedding", "confidence", "tracklet_id", "global_track_id", "floor_point", "pose_keypoints", "trail", "evidence", "floor_x", "floor_y")
    DETECTION_ID_FIELD_NUMBER: _ClassVar[int]
    BBOX_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    TRACKLET_ID_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    FLOOR_POINT_FIELD_NUMBER: _ClassVar[int]
    POSE_KEYPOINTS_FIELD_NUMBER: _ClassVar[int]
    TRAIL_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_FIELD_NUMBER: _ClassVar[int]
    FLOOR_X_FIELD_NUMBER: _ClassVar[int]
    FLOOR_Y_FIELD_NUMBER: _ClassVar[int]
    detection_id: str
    bbox: BoundingBox
    embedding: _containers.RepeatedScalarFieldContainer[float]
    confidence: float
    tracklet_id: str
    global_track_id: str
    floor_point: FloorPoint
    pose_keypoints: _containers.RepeatedCompositeFieldContainer[PoseKeypoint]
    trail: _containers.RepeatedCompositeFieldContainer[TrailPoint]
    evidence: PosteriorEvidence
    floor_x: float
    floor_y: float
    def __init__(self, detection_id: _Optional[str] = ..., bbox: _Optional[_Union[BoundingBox, _Mapping]] = ..., embedding: _Optional[_Iterable[float]] = ..., confidence: _Optional[float] = ..., tracklet_id: _Optional[str] = ..., global_track_id: _Optional[str] = ..., floor_point: _Optional[_Union[FloorPoint, _Mapping]] = ..., pose_keypoints: _Optional[_Iterable[_Union[PoseKeypoint, _Mapping]]] = ..., trail: _Optional[_Iterable[_Union[TrailPoint, _Mapping]]] = ..., evidence: _Optional[_Union[PosteriorEvidence, _Mapping]] = ..., floor_x: _Optional[float] = ..., floor_y: _Optional[float] = ...) -> None: ...

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
    __slots__ = ("global_track_id", "candidates", "map_identity_id", "posterior_entropy", "revision_time_unix_ns", "revision_id", "tracklet_ids", "previous_identity_id", "new_identity_id", "reason", "evidence_json")
    GLOBAL_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    CANDIDATES_FIELD_NUMBER: _ClassVar[int]
    MAP_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    POSTERIOR_ENTROPY_FIELD_NUMBER: _ClassVar[int]
    REVISION_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    REVISION_ID_FIELD_NUMBER: _ClassVar[int]
    TRACKLET_IDS_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    NEW_IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_JSON_FIELD_NUMBER: _ClassVar[int]
    global_track_id: str
    candidates: _containers.RepeatedCompositeFieldContainer[IdentityCandidate]
    map_identity_id: str
    posterior_entropy: float
    revision_time_unix_ns: int
    revision_id: str
    tracklet_ids: _containers.RepeatedScalarFieldContainer[str]
    previous_identity_id: str
    new_identity_id: str
    reason: str
    evidence_json: str
    def __init__(self, global_track_id: _Optional[str] = ..., candidates: _Optional[_Iterable[_Union[IdentityCandidate, _Mapping]]] = ..., map_identity_id: _Optional[str] = ..., posterior_entropy: _Optional[float] = ..., revision_time_unix_ns: _Optional[int] = ..., revision_id: _Optional[str] = ..., tracklet_ids: _Optional[_Iterable[str]] = ..., previous_identity_id: _Optional[str] = ..., new_identity_id: _Optional[str] = ..., reason: _Optional[str] = ..., evidence_json: _Optional[str] = ...) -> None: ...

class IdentityCandidate(_message.Message):
    __slots__ = ("identity_id", "display_name", "probability")
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    identity_id: str
    display_name: str
    probability: float
    def __init__(self, identity_id: _Optional[str] = ..., display_name: _Optional[str] = ..., probability: _Optional[float] = ...) -> None: ...
