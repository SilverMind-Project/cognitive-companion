from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AnonymousPositionTrack(_message.Message):
    __slots__ = ("sensor_id", "sensor_track_id", "measured_at_unix_ns", "x_mm", "y_mm", "cov_xx_m2", "cov_xy_m2", "cov_yy_m2", "has_speed", "speed_m_s", "floor_plan_id")
    SENSOR_ID_FIELD_NUMBER: _ClassVar[int]
    SENSOR_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    MEASURED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    X_MM_FIELD_NUMBER: _ClassVar[int]
    Y_MM_FIELD_NUMBER: _ClassVar[int]
    COV_XX_M2_FIELD_NUMBER: _ClassVar[int]
    COV_XY_M2_FIELD_NUMBER: _ClassVar[int]
    COV_YY_M2_FIELD_NUMBER: _ClassVar[int]
    HAS_SPEED_FIELD_NUMBER: _ClassVar[int]
    SPEED_M_S_FIELD_NUMBER: _ClassVar[int]
    FLOOR_PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    sensor_id: str
    sensor_track_id: str
    measured_at_unix_ns: int
    x_mm: int
    y_mm: int
    cov_xx_m2: float
    cov_xy_m2: float
    cov_yy_m2: float
    has_speed: bool
    speed_m_s: float
    floor_plan_id: str
    def __init__(self, sensor_id: _Optional[str] = ..., sensor_track_id: _Optional[str] = ..., measured_at_unix_ns: _Optional[int] = ..., x_mm: _Optional[int] = ..., y_mm: _Optional[int] = ..., cov_xx_m2: _Optional[float] = ..., cov_xy_m2: _Optional[float] = ..., cov_yy_m2: _Optional[float] = ..., has_speed: bool = ..., speed_m_s: _Optional[float] = ..., floor_plan_id: _Optional[str] = ...) -> None: ...
