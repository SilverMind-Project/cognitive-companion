from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PresenceStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRESENCE_STATUS_UNSPECIFIED: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_PRESENT_ROOM: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_PRESENT_HOME: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_AWAY: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_ASLEEP: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_UNKNOWN: _ClassVar[PresenceStatus]
    PRESENCE_STATUS_STALE: _ClassVar[PresenceStatus]
PRESENCE_STATUS_UNSPECIFIED: PresenceStatus
PRESENCE_STATUS_PRESENT_ROOM: PresenceStatus
PRESENCE_STATUS_PRESENT_HOME: PresenceStatus
PRESENCE_STATUS_AWAY: PresenceStatus
PRESENCE_STATUS_ASLEEP: PresenceStatus
PRESENCE_STATUS_UNKNOWN: PresenceStatus
PRESENCE_STATUS_STALE: PresenceStatus

class MemberPresence(_message.Message):
    __slots__ = ("member_id", "status", "confidence", "room_id", "inferred_at_unix_ns")
    MEMBER_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    ROOM_ID_FIELD_NUMBER: _ClassVar[int]
    INFERRED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    member_id: str
    status: PresenceStatus
    confidence: float
    room_id: str
    inferred_at_unix_ns: int
    def __init__(self, member_id: _Optional[str] = ..., status: _Optional[_Union[PresenceStatus, str]] = ..., confidence: _Optional[float] = ..., room_id: _Optional[str] = ..., inferred_at_unix_ns: _Optional[int] = ...) -> None: ...

class HouseholdPresence(_message.Message):
    __slots__ = ("members", "roster_complete", "visitors_present", "published_at_unix_ns")
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    ROSTER_COMPLETE_FIELD_NUMBER: _ClassVar[int]
    VISITORS_PRESENT_FIELD_NUMBER: _ClassVar[int]
    PUBLISHED_AT_UNIX_NS_FIELD_NUMBER: _ClassVar[int]
    members: _containers.RepeatedCompositeFieldContainer[MemberPresence]
    roster_complete: bool
    visitors_present: bool
    published_at_unix_ns: int
    def __init__(self, members: _Optional[_Iterable[_Union[MemberPresence, _Mapping]]] = ..., roster_complete: bool = ..., visitors_present: bool = ..., published_at_unix_ns: _Optional[int] = ...) -> None: ...
