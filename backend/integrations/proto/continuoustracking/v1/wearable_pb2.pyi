from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FixKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FIX_KIND_UNSPECIFIED: _ClassVar[FixKind]
    FIX_KIND_POSITION: _ClassVar[FixKind]
    FIX_KIND_ROOM: _ClassVar[FixKind]
    FIX_KIND_PROXIMITY: _ClassVar[FixKind]

class AdapterKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ADAPTER_KIND_UNSPECIFIED: _ClassVar[AdapterKind]
    ADAPTER_KIND_DEVICE_RANGING: _ClassVar[AdapterKind]
    ADAPTER_KIND_ANCHOR_RANGING: _ClassVar[AdapterKind]
    ADAPTER_KIND_SOLVED_POSITION: _ClassVar[AdapterKind]
    ADAPTER_KIND_ROOM_PRESENCE: _ClassVar[AdapterKind]
    ADAPTER_KIND_SIMULATOR: _ClassVar[AdapterKind]

class WearState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WEAR_STATE_UNSPECIFIED: _ClassVar[WearState]
    WEAR_STATE_ON_BODY: _ClassVar[WearState]
    WEAR_STATE_OFF_BODY: _ClassVar[WearState]

class MotionState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MOTION_STATE_UNSPECIFIED: _ClassVar[MotionState]
    MOTION_STATE_MOVING: _ClassVar[MotionState]
    MOTION_STATE_STILL: _ClassVar[MotionState]

class RfNodeRole(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RF_NODE_ROLE_UNSPECIFIED: _ClassVar[RfNodeRole]
    RF_NODE_ROLE_RECEIVER: _ClassVar[RfNodeRole]
    RF_NODE_ROLE_RANGING_ANCHOR: _ClassVar[RfNodeRole]

class RangingTechnology(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RANGING_TECHNOLOGY_UNSPECIFIED: _ClassVar[RangingTechnology]
    RANGING_TECHNOLOGY_BLE_RSSI: _ClassVar[RangingTechnology]
    RANGING_TECHNOLOGY_BLE_CHANNEL_SOUNDING: _ClassVar[RangingTechnology]
    RANGING_TECHNOLOGY_UWB: _ClassVar[RangingTechnology]
FIX_KIND_UNSPECIFIED: FixKind
FIX_KIND_POSITION: FixKind
FIX_KIND_ROOM: FixKind
FIX_KIND_PROXIMITY: FixKind
ADAPTER_KIND_UNSPECIFIED: AdapterKind
ADAPTER_KIND_DEVICE_RANGING: AdapterKind
ADAPTER_KIND_ANCHOR_RANGING: AdapterKind
ADAPTER_KIND_SOLVED_POSITION: AdapterKind
ADAPTER_KIND_ROOM_PRESENCE: AdapterKind
ADAPTER_KIND_SIMULATOR: AdapterKind
WEAR_STATE_UNSPECIFIED: WearState
WEAR_STATE_ON_BODY: WearState
WEAR_STATE_OFF_BODY: WearState
MOTION_STATE_UNSPECIFIED: MotionState
MOTION_STATE_MOVING: MotionState
MOTION_STATE_STILL: MotionState
RF_NODE_ROLE_UNSPECIFIED: RfNodeRole
RF_NODE_ROLE_RECEIVER: RfNodeRole
RF_NODE_ROLE_RANGING_ANCHOR: RfNodeRole
RANGING_TECHNOLOGY_UNSPECIFIED: RangingTechnology
RANGING_TECHNOLOGY_BLE_RSSI: RangingTechnology
RANGING_TECHNOLOGY_BLE_CHANNEL_SOUNDING: RangingTechnology
RANGING_TECHNOLOGY_UWB: RangingTechnology

class TagFix(_message.Message):
    __slots__ = ("tag_id", "measured_at_unix_ns", "kind", "epoch_seq", "has_position", "x_mm", "y_mm", "has_z", "z_mm", "cov_xx_m2", "cov_xy_m2", "cov_yy_m2", "floor_plan_id", "room_id", "has_room_probability", "room_probability", "anchor_id", "has_distance", "distance_m", "wear_state", "has_quality", "quality", "anchors_used", "has_residual", "residual_rms_m", "adapter_id", "adapter_kind", "adapter_version", "motion_state", "has_battery", "battery_fraction")
    TAG_ID_FIELD_NUMBER: _ClassVar[int]
    MEASURED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    EPOCH_SEQ_FIELD_NUMBER: _ClassVar[int]
    HAS_POSITION_FIELD_NUMBER: _ClassVar[int]
    X_MM_FIELD_NUMBER: _ClassVar[int]
    Y_MM_FIELD_NUMBER: _ClassVar[int]
    HAS_Z_FIELD_NUMBER: _ClassVar[int]
    Z_MM_FIELD_NUMBER: _ClassVar[int]
    COV_XX_M2_FIELD_NUMBER: _ClassVar[int]
    COV_XY_M2_FIELD_NUMBER: _ClassVar[int]
    COV_YY_M2_FIELD_NUMBER: _ClassVar[int]
    FLOOR_PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    ROOM_ID_FIELD_NUMBER: _ClassVar[int]
    HAS_ROOM_PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    ROOM_PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    ANCHOR_ID_FIELD_NUMBER: _ClassVar[int]
    HAS_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_M_FIELD_NUMBER: _ClassVar[int]
    WEAR_STATE_FIELD_NUMBER: _ClassVar[int]
    HAS_QUALITY_FIELD_NUMBER: _ClassVar[int]
    QUALITY_FIELD_NUMBER: _ClassVar[int]
    ANCHORS_USED_FIELD_NUMBER: _ClassVar[int]
    HAS_RESIDUAL_FIELD_NUMBER: _ClassVar[int]
    RESIDUAL_RMS_M_FIELD_NUMBER: _ClassVar[int]
    ADAPTER_ID_FIELD_NUMBER: _ClassVar[int]
    ADAPTER_KIND_FIELD_NUMBER: _ClassVar[int]
    ADAPTER_VERSION_FIELD_NUMBER: _ClassVar[int]
    MOTION_STATE_FIELD_NUMBER: _ClassVar[int]
    HAS_BATTERY_FIELD_NUMBER: _ClassVar[int]
    BATTERY_FRACTION_FIELD_NUMBER: _ClassVar[int]
    tag_id: str
    measured_at_unix_ns: int
    kind: FixKind
    epoch_seq: int
    has_position: bool
    x_mm: int
    y_mm: int
    has_z: bool
    z_mm: int
    cov_xx_m2: float
    cov_xy_m2: float
    cov_yy_m2: float
    floor_plan_id: str
    room_id: str
    has_room_probability: bool
    room_probability: float
    anchor_id: str
    has_distance: bool
    distance_m: float
    wear_state: WearState
    has_quality: bool
    quality: float
    anchors_used: int
    has_residual: bool
    residual_rms_m: float
    adapter_id: str
    adapter_kind: AdapterKind
    adapter_version: str
    motion_state: MotionState
    has_battery: bool
    battery_fraction: float
    def __init__(self, tag_id: _Optional[str] = ..., measured_at_unix_ns: _Optional[int] = ..., kind: _Optional[_Union[FixKind, str]] = ..., epoch_seq: _Optional[int] = ..., has_position: bool = ..., x_mm: _Optional[int] = ..., y_mm: _Optional[int] = ..., has_z: bool = ..., z_mm: _Optional[int] = ..., cov_xx_m2: _Optional[float] = ..., cov_xy_m2: _Optional[float] = ..., cov_yy_m2: _Optional[float] = ..., floor_plan_id: _Optional[str] = ..., room_id: _Optional[str] = ..., has_room_probability: bool = ..., room_probability: _Optional[float] = ..., anchor_id: _Optional[str] = ..., has_distance: bool = ..., distance_m: _Optional[float] = ..., wear_state: _Optional[_Union[WearState, str]] = ..., has_quality: bool = ..., quality: _Optional[float] = ..., anchors_used: _Optional[int] = ..., has_residual: bool = ..., residual_rms_m: _Optional[float] = ..., adapter_id: _Optional[str] = ..., adapter_kind: _Optional[_Union[AdapterKind, str]] = ..., adapter_version: _Optional[str] = ..., motion_state: _Optional[_Union[MotionState, str]] = ..., has_battery: bool = ..., battery_fraction: _Optional[float] = ...) -> None: ...

class AdapterCapability(_message.Message):
    __slots__ = ("adapter_id", "adapter_kind", "fix_kinds", "nominal_rate_hz", "reports_covariance", "reports_wear_state", "reports_z", "reported_at_unix_ns", "reports_motion_state")
    ADAPTER_ID_FIELD_NUMBER: _ClassVar[int]
    ADAPTER_KIND_FIELD_NUMBER: _ClassVar[int]
    FIX_KINDS_FIELD_NUMBER: _ClassVar[int]
    NOMINAL_RATE_HZ_FIELD_NUMBER: _ClassVar[int]
    REPORTS_COVARIANCE_FIELD_NUMBER: _ClassVar[int]
    REPORTS_WEAR_STATE_FIELD_NUMBER: _ClassVar[int]
    REPORTS_Z_FIELD_NUMBER: _ClassVar[int]
    REPORTED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    REPORTS_MOTION_STATE_FIELD_NUMBER: _ClassVar[int]
    adapter_id: str
    adapter_kind: AdapterKind
    fix_kinds: _containers.RepeatedScalarFieldContainer[FixKind]
    nominal_rate_hz: float
    reports_covariance: bool
    reports_wear_state: bool
    reports_z: bool
    reported_at_unix_ns: int
    reports_motion_state: bool
    def __init__(self, adapter_id: _Optional[str] = ..., adapter_kind: _Optional[_Union[AdapterKind, str]] = ..., fix_kinds: _Optional[_Iterable[_Union[FixKind, str]]] = ..., nominal_rate_hz: _Optional[float] = ..., reports_covariance: bool = ..., reports_wear_state: bool = ..., reports_z: bool = ..., reported_at_unix_ns: _Optional[int] = ..., reports_motion_state: bool = ...) -> None: ...
