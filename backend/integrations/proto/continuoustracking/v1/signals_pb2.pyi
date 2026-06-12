from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DementiaSignalKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DEMENTIA_SIGNAL_KIND_UNSPECIFIED: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_PACING: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_SUNDOWNING_INDEX: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_BATHROOM_DWELL_ANOMALY: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_NIGHTTIME_MOVEMENT: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_STILLNESS_ANOMALY: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_ABSENCE: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_FALL_SUSPECTED: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_GAIT_SLOWING: _ClassVar[DementiaSignalKind]
    DEMENTIA_SIGNAL_KIND_AGITATION_INDEX: _ClassVar[DementiaSignalKind]

class DementiaSignalSeverity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DEMENTIA_SIGNAL_SEVERITY_UNSPECIFIED: _ClassVar[DementiaSignalSeverity]
    DEMENTIA_SIGNAL_SEVERITY_INFO: _ClassVar[DementiaSignalSeverity]
    DEMENTIA_SIGNAL_SEVERITY_WARNING: _ClassVar[DementiaSignalSeverity]
    DEMENTIA_SIGNAL_SEVERITY_EMERGENCY: _ClassVar[DementiaSignalSeverity]
DEMENTIA_SIGNAL_KIND_UNSPECIFIED: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_PACING: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_SUNDOWNING_INDEX: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_BATHROOM_DWELL_ANOMALY: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_NIGHTTIME_MOVEMENT: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_STILLNESS_ANOMALY: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_ABSENCE: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_FALL_SUSPECTED: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_GAIT_SLOWING: DementiaSignalKind
DEMENTIA_SIGNAL_KIND_AGITATION_INDEX: DementiaSignalKind
DEMENTIA_SIGNAL_SEVERITY_UNSPECIFIED: DementiaSignalSeverity
DEMENTIA_SIGNAL_SEVERITY_INFO: DementiaSignalSeverity
DEMENTIA_SIGNAL_SEVERITY_WARNING: DementiaSignalSeverity
DEMENTIA_SIGNAL_SEVERITY_EMERGENCY: DementiaSignalSeverity

class DementiaSignal(_message.Message):
    __slots__ = ("signal_id", "identity_id", "kind", "severity", "value", "has_baseline", "baseline", "has_z_score", "z_score", "window_start_unix_ns", "window_end_unix_ns", "emitted_at_unix_ns", "context_json", "algorithm_version", "algorithm_name", "evidence_grade", "algorithm_spec_json")
    SIGNAL_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    HAS_BASELINE_FIELD_NUMBER: _ClassVar[int]
    BASELINE_FIELD_NUMBER: _ClassVar[int]
    HAS_Z_SCORE_FIELD_NUMBER: _ClassVar[int]
    Z_SCORE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_START_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    WINDOW_END_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    EMITTED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_JSON_FIELD_NUMBER: _ClassVar[int]
    ALGORITHM_VERSION_FIELD_NUMBER: _ClassVar[int]
    ALGORITHM_NAME_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_GRADE_FIELD_NUMBER: _ClassVar[int]
    ALGORITHM_SPEC_JSON_FIELD_NUMBER: _ClassVar[int]
    signal_id: str
    identity_id: str
    kind: DementiaSignalKind
    severity: DementiaSignalSeverity
    value: float
    has_baseline: bool
    baseline: float
    has_z_score: bool
    z_score: float
    window_start_unix_ns: int
    window_end_unix_ns: int
    emitted_at_unix_ns: int
    context_json: str
    algorithm_version: int
    algorithm_name: str
    evidence_grade: str
    algorithm_spec_json: str
    def __init__(self, signal_id: _Optional[str] = ..., identity_id: _Optional[str] = ..., kind: _Optional[_Union[DementiaSignalKind, str]] = ..., severity: _Optional[_Union[DementiaSignalSeverity, str]] = ..., value: _Optional[float] = ..., has_baseline: bool = ..., baseline: _Optional[float] = ..., has_z_score: bool = ..., z_score: _Optional[float] = ..., window_start_unix_ns: _Optional[int] = ..., window_end_unix_ns: _Optional[int] = ..., emitted_at_unix_ns: _Optional[int] = ..., context_json: _Optional[str] = ..., algorithm_version: _Optional[int] = ..., algorithm_name: _Optional[str] = ..., evidence_grade: _Optional[str] = ..., algorithm_spec_json: _Optional[str] = ...) -> None: ...
