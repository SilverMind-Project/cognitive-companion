from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TagReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TAG_REASON_UNSPECIFIED: _ClassVar[TagReason]
    TAG_REASON_PERIODIC: _ClassVar[TagReason]
    TAG_REASON_IDENTITY_CHANGED: _ClassVar[TagReason]
    TAG_REASON_HAZARD: _ClassVar[TagReason]
    TAG_REASON_DWELL_START: _ClassVar[TagReason]
    TAG_REASON_FALL: _ClassVar[TagReason]
    TAG_REASON_DEMENTIA_SIGNAL: _ClassVar[TagReason]
TAG_REASON_UNSPECIFIED: TagReason
TAG_REASON_PERIODIC: TagReason
TAG_REASON_IDENTITY_CHANGED: TagReason
TAG_REASON_HAZARD: TagReason
TAG_REASON_DWELL_START: TagReason
TAG_REASON_FALL: TagReason
TAG_REASON_DEMENTIA_SIGNAL: TagReason

class SceneSample(_message.Message):
    __slots__ = ("keyframe_id", "camera_id", "minio_key", "captured_at_unix_ns", "tag_reason", "annotations_json", "expires_at_unix_ns", "ph_id")
    KEYFRAME_ID_FIELD_NUMBER: _ClassVar[int]
    CAMERA_ID_FIELD_NUMBER: _ClassVar[int]
    MINIO_KEY_FIELD_NUMBER: _ClassVar[int]
    CAPTURED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    TAG_REASON_FIELD_NUMBER: _ClassVar[int]
    ANNOTATIONS_JSON_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    PH_ID_FIELD_NUMBER: _ClassVar[int]
    keyframe_id: str
    camera_id: str
    minio_key: str
    captured_at_unix_ns: int
    tag_reason: TagReason
    annotations_json: str
    expires_at_unix_ns: int
    ph_id: str
    def __init__(self, keyframe_id: _Optional[str] = ..., camera_id: _Optional[str] = ..., minio_key: _Optional[str] = ..., captured_at_unix_ns: _Optional[int] = ..., tag_reason: _Optional[_Union[TagReason, str]] = ..., annotations_json: _Optional[str] = ..., expires_at_unix_ns: _Optional[int] = ..., ph_id: _Optional[str] = ...) -> None: ...
