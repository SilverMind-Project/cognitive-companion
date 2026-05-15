from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FrameReady(_message.Message):
    __slots__ = ("camera_id", "minio_key", "frame_index", "capture_time_unix_ns", "received_time_unix_ns", "width", "height", "sample_fps")
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    MINIO_KEY_FIELD_NUMBER: _ClassVar[int]
    FRAME_INDEX_FIELD_NUMBER: _ClassVar[int]
    CAPTURE_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_FPS_FIELD_NUMBER: _ClassVar[int]
    camera_id: str
    minio_key: str
    frame_index: int
    capture_time_unix_ns: int
    received_time_unix_ns: int
    width: int
    height: int
    sample_fps: float
    def __init__(self, camera_id: _Optional[str] = ..., minio_key: _Optional[str] = ..., frame_index: _Optional[int] = ..., capture_time_unix_ns: _Optional[int] = ..., received_time_unix_ns: _Optional[int] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., sample_fps: _Optional[float] = ...) -> None: ...

class FrameResponse(_message.Message):
    __slots__ = ("camera_id", "frame_index", "success", "error_code", "processing_latency_us", "detection_count", "completed_time_unix_ns")
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_INDEX_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_LATENCY_US_FIELD_NUMBER: _ClassVar[int]
    DETECTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_TIME_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    camera_id: str
    frame_index: int
    success: bool
    error_code: str
    processing_latency_us: int
    detection_count: int
    completed_time_unix_ns: int
    def __init__(self, camera_id: _Optional[str] = ..., frame_index: _Optional[int] = ..., success: bool = ..., error_code: _Optional[str] = ..., processing_latency_us: _Optional[int] = ..., detection_count: _Optional[int] = ..., completed_time_unix_ns: _Optional[int] = ...) -> None: ...
