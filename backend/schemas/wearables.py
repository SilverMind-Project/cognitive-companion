"""Pydantic v2 schemas for wearable devices, bindings, RF nodes, position sensors, and site config."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from cts_contracts import (
    SENSOR_ID_PATTERN,
    DeviceKind,
    PositionSensorModality,
    RangingTechnology,
    RfNodeRole,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_UWB_HEX_RE = re.compile(r"^[0-9a-fA-F]{2}:[0-9a-fA-F]{2}$")
_SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


def _optional_slug(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _SAFE_SLUG_RE.match(value):
        raise ValueError("must contain only letters, digits, or . _ : @ / -")
    return value


def _validate_non_empty(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


class WearableDeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_id: str = Field(min_length=1, max_length=128)
    device_kind: DeviceKind
    label: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(min_length=1, max_length=128)
    hardware_key: str = Field(min_length=1, max_length=256)
    # Shared by the logical tags of one radio (a dual-mode watch's BLE and UWB tags).
    physical_device_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("tag_id", "adapter_id")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        v = v.strip()
        if not _SAFE_SLUG_RE.match(v):
            raise ValueError("must contain only letters, digits, or . _ : @ / -")
        return v

    @field_validator("physical_device_id")
    @classmethod
    def _check_physical_slug(cls, v: str | None) -> str | None:
        return _optional_slug(v)

    @field_validator("label", "hardware_key")
    @classmethod
    def _check_non_empty(cls, v: str, info) -> str:
        return _validate_non_empty(v, info.field_name)


class WearableDeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    device_kind: DeviceKind | None = None
    adapter_id: str | None = Field(default=None, min_length=1, max_length=128)
    hardware_key: str | None = Field(default=None, min_length=1, max_length=256)
    # Explicit null clears the link; omitting the field leaves it unchanged.
    physical_device_id: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None

    @field_validator("physical_device_id")
    @classmethod
    def _check_physical_slug(cls, v: str | None) -> str | None:
        return _optional_slug(v)

    @field_validator("adapter_id")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _SAFE_SLUG_RE.match(v):
            raise ValueError("must contain only letters, digits, or . _ : @ / -")
        return v

    @field_validator("label", "hardware_key")
    @classmethod
    def _check_non_empty(cls, v: str | None, info) -> str | None:
        if v is None:
            return None
        return _validate_non_empty(v, info.field_name)


class WearableBindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    tag_id: str
    member_id: str | None
    member_name: str | None = None
    valid_from: datetime
    valid_to: datetime | None
    consent_recorded_by: str
    consent_recorded_at: datetime
    created_by: str


class WearableDeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tag_id: str
    device_kind: DeviceKind
    label: str
    adapter_id: str
    hardware_key: str
    physical_device_id: str | None = None
    is_active: bool
    last_heard_at: datetime | None
    last_battery_fraction: float | None
    active_binding: WearableBindingOut | None = None
    created_at: datetime
    updated_at: datetime


class WearableDeviceListOut(BaseModel):
    items: list[WearableDeviceOut]
    total: int = Field(ge=0)


class WearableBindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: str = Field(min_length=1, max_length=64)
    consent_confirmed: bool = Field(
        description="Explicit caregiver confirmation that consent was obtained for wearing this tag"
    )
    consent_recorded_by: str = Field(min_length=1, max_length=128)
    valid_from: datetime | None = None

    @field_validator("consent_confirmed")
    @classmethod
    def _must_confirm_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Explicit consent confirmation is required before binding a wearable")
        return v

    @field_validator("member_id", "consent_recorded_by")
    @classmethod
    def _check_non_empty(cls, v: str, info) -> str:
        return _validate_non_empty(v, info.field_name)


class WearableUnbindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime | None = None


class MemberWearableDeviceSummary(BaseModel):
    device_id: uuid.UUID
    tag_id: str
    label: str
    device_kind: DeviceKind
    adapter_id: str
    physical_device_id: str | None = None
    is_active: bool
    valid_from: datetime
    consent_recorded_by: str
    last_heard_at: datetime | None
    last_battery_fraction: float | None


class MemberWearablesOut(BaseModel):
    member_id: str
    member_name: str
    devices: list[MemberWearableDeviceSummary]


class WearableAssignmentsOut(BaseModel):
    members: list[MemberWearablesOut]
    unbound_devices: list[WearableDeviceOut]
    checked_at: datetime


class WearableDeviceStatusOut(BaseModel):
    device_id: uuid.UUID
    tag_id: str
    label: str
    device_kind: DeviceKind
    adapter_id: str
    is_active: bool
    bound_member_id: str | None
    bound_member_name: str | None
    reporting: bool
    last_heard_at: datetime | None
    last_heard_age_s: float | None
    last_battery_fraction: float | None
    checked_at: datetime


class RfNodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(min_length=1, max_length=128)
    node_role: RfNodeRole
    technology: RangingTechnology
    room_id: int | None = None
    x_norm: float = Field(ge=0.0, le=1.0)
    y_norm: float = Field(ge=0.0, le=1.0)
    z_m: float = Field(ge=0.0, le=4.0)
    is_active: bool = True
    placement_residual_m: float | None = Field(default=None, ge=0.0)
    firmware_version: str | None = Field(default=None, max_length=128)
    uwb_address_hex: str | None = Field(default=None, max_length=8)
    uwb_channel: int | None = None
    uwb_preamble_index: int | None = None

    @field_validator("anchor_id", "adapter_id")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        v = v.strip()
        if not _SAFE_SLUG_RE.match(v):
            raise ValueError("must contain only letters, digits, or . _ : @ / -")
        return v

    @field_validator("label")
    @classmethod
    def _check_label(cls, v: str) -> str:
        return _validate_non_empty(v, "label")

    @field_validator("firmware_version")
    @classmethod
    def _check_firmware_version(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @field_validator("uwb_address_hex")
    @classmethod
    def _check_uwb_addr(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not _UWB_HEX_RE.match(v):
            raise ValueError("uwb_address_hex must match XX:XX hexadecimal format (e.g. 00:01)")
        return v

    @field_validator("uwb_channel")
    @classmethod
    def _check_uwb_channel(cls, v: int | None) -> int | None:
        if v is not None and v not in (5, 9):
            raise ValueError("uwb_channel must be 5 or 9")
        return v

    @field_validator("uwb_preamble_index")
    @classmethod
    def _check_uwb_preamble(cls, v: int | None) -> int | None:
        if v is not None and not (9 <= v <= 32):
            raise ValueError("uwb_preamble_index must be between 9 and 32")
        return v

    @model_validator(mode="after")
    def _check_uwb_defaults(self) -> RfNodeCreate:
        if self.technology == RangingTechnology.UWB:
            if self.uwb_channel is None:
                self.uwb_channel = 9
            if self.uwb_preamble_index is None:
                self.uwb_preamble_index = 10
        return self


class RfNodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    adapter_id: str | None = Field(default=None, min_length=1, max_length=128)
    node_role: RfNodeRole | None = None
    technology: RangingTechnology | None = None
    room_id: int | None = None
    x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    z_m: float | None = Field(default=None, ge=0.0, le=4.0)
    is_active: bool | None = None
    placement_residual_m: float | None = Field(default=None, ge=0.0)
    firmware_version: str | None = Field(default=None, max_length=128)
    uwb_address_hex: str | None = Field(default=None, max_length=8)
    uwb_channel: int | None = None
    uwb_preamble_index: int | None = None

    @field_validator("adapter_id")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _SAFE_SLUG_RE.match(v):
            raise ValueError("must contain only letters, digits, or . _ : @ / -")
        return v

    @field_validator("label")
    @classmethod
    def _check_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_non_empty(v, "label")

    @field_validator("firmware_version")
    @classmethod
    def _check_firmware_version(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @field_validator("uwb_address_hex")
    @classmethod
    def _check_uwb_addr(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not _UWB_HEX_RE.match(v):
            raise ValueError("uwb_address_hex must match XX:XX hexadecimal format (e.g. 00:01)")
        return v

    @field_validator("uwb_channel")
    @classmethod
    def _check_uwb_channel(cls, v: int | None) -> int | None:
        if v is not None and v not in (5, 9):
            raise ValueError("uwb_channel must be 5 or 9")
        return v

    @field_validator("uwb_preamble_index")
    @classmethod
    def _check_uwb_preamble(cls, v: int | None) -> int | None:
        if v is not None and not (9 <= v <= 32):
            raise ValueError("uwb_preamble_index must be between 9 and 32")
        return v


class RfNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    anchor_id: str
    label: str
    adapter_id: str
    node_role: RfNodeRole
    technology: RangingTechnology
    room_id: int | None
    room_name: str | None = None
    x_norm: float
    y_norm: float
    x_m: float | None = None
    y_m: float | None = None
    z_m: float
    is_active: bool
    placement_residual_m: float | None
    firmware_version: str | None = None
    last_heard_at: datetime | None = None
    last_heard_age_s: float | None = None
    uwb_address_hex: str | None
    uwb_channel: int | None
    uwb_preamble_index: int | None
    created_at: datetime
    updated_at: datetime


class RfNodeListOut(BaseModel):
    items: list[RfNodeOut]
    total: int = Field(ge=0)
    floor_plan_ready: bool
    floor_plan_id: str | None
    floor_width_m: float | None
    floor_height_m: float | None


def _check_sensor_id(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(SENSOR_ID_PATTERN, value):
        raise ValueError(
            "must be 1 to 64 lowercase letters, digits, or . _ - starting with a letter or digit"
        )
    return value


class PositionSensorCreate(BaseModel):
    """Register a device-free position sensor (mmWave radar or room LiDAR)."""

    model_config = ConfigDict(extra="forbid")

    sensor_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    modality: PositionSensorModality
    room_id: int
    x_norm: float = Field(ge=0.0, le=1.0)
    y_norm: float = Field(ge=0.0, le=1.0)
    yaw_deg: float | None = Field(default=None, ge=-180.0, lt=180.0)
    calibration_residual_m: float = Field(default=0.10, gt=0.0, le=1.0)
    is_active: bool = True

    @field_validator("sensor_id")
    @classmethod
    def _validate_sensor_id(cls, v: str) -> str:
        return _check_sensor_id(v)

    @field_validator("label")
    @classmethod
    def _check_label(cls, v: str) -> str:
        return _validate_non_empty(v, "label")


class PositionSensorUpdate(BaseModel):
    """Partial update of a position sensor; ``sensor_id`` is immutable (gateways publish it)."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    modality: PositionSensorModality | None = None
    room_id: int | None = None
    x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    yaw_deg: float | None = Field(default=None, ge=-180.0, lt=180.0)
    calibration_residual_m: float | None = Field(default=None, gt=0.0, le=1.0)
    is_active: bool | None = None

    @field_validator("label")
    @classmethod
    def _check_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_non_empty(v, "label")


class PositionSensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: str
    label: str
    modality: PositionSensorModality
    room_id: int | None
    room_name: str | None = None
    x_norm: float
    y_norm: float
    x_m: float | None = None
    y_m: float | None = None
    yaw_deg: float | None
    calibration_residual_m: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PositionSensorListOut(BaseModel):
    items: list[PositionSensorOut]
    total: int = Field(ge=0)
    floor_plan_ready: bool


class SurveyDistanceMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_kind: Literal["wall", "node"]
    reference_id: str = Field(min_length=1, max_length=128)
    measured_m: float = Field(ge=0.0, le=100.0)


class RfNodeSurveyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_norm: float = Field(ge=0.0, le=1.0)
    y_norm: float = Field(ge=0.0, le=1.0)
    z_m: float = Field(ge=0.0, le=4.0, default=1.5)
    measurements: list[SurveyDistanceMeasurement] = Field(min_length=2, max_length=8)


class RfNodeSurveyCheckItemOut(BaseModel):
    reference_kind: Literal["wall", "node"]
    reference_id: str
    measured_m: float
    expected_m: float
    discrepancy_m: float
    exceeds_tolerance: bool


class RfNodeSurveyCheckOut(BaseModel):
    x_m: float
    y_m: float
    z_m: float
    tolerance_m: float
    max_discrepancy_m: float
    warning: bool
    checks: list[RfNodeSurveyCheckItemOut]


class SiteConfigNodeOut(BaseModel):
    anchor_id: str
    adapter_id: str
    node_role: RfNodeRole
    technology: RangingTechnology
    x_m: float
    y_m: float
    z_m: float
    room_id: str | None = None
    uwb_address_hex: str | None = None
    uwb_channel: int | None = None
    uwb_preamble_index: int | None = None


class SiteConfigBindingOut(BaseModel):
    tag_id: str
    member_id: str
    valid_from: datetime
    valid_to: datetime | None


class SiteConfigDeviceOut(BaseModel):
    tag_id: str
    adapter_id: str
    hardware_key: str
    device_kind: DeviceKind
    is_active: bool
    # Logical tags sharing this value are one radio; CTS treats them as one wearable.
    physical_device_id: str | None = None


class SiteConfigPositionSensorOut(BaseModel):
    """One active device-free position sensor, its mounting pose in metres on the floor plan."""

    sensor_id: str
    room_id: str | None = None
    x_m: float
    y_m: float
    # Null when the sensor's gateway reports in floor-plan coordinates and needs no pose.
    yaw_deg: float | None = None
    calibration_residual_m: float


class WearableSiteConfigOut(BaseModel):
    floor_plan_id: str | None
    nodes: list[SiteConfigNodeOut]
    bindings: list[SiteConfigBindingOut]
    devices: list[SiteConfigDeviceOut]
    # Active position sensors; empty without a floor-plan scale (metres are undefined).
    position_sensors: list[SiteConfigPositionSensorOut] = Field(default_factory=list)
    version: str


class WearableTeachingHoldOut(BaseModel):
    hold_id: str
    tag_id: str
    reason: str
    held_at: datetime
    cleared_at: datetime | None = None
    cleared_by: str | None = None


class PromotedAttestationOut(BaseModel):
    candidate_id: str
    person_id: str | None = None
    pose_bin: str = "frontal"


class WearableAssociationTaughtOut(BaseModel):
    segment_id: str
    ph_id: str
    tag_id: str
    identity_id: str
    started_at: datetime
    ended_at: datetime | None = None
    attestation_grade: str
    swap_suspected: bool = False
    close_reason: str | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None
    gallery_rows_by_state: dict[str, int] = Field(default_factory=dict)
    gallery_rows_total: int = Field(default=0, ge=0)
    attested_faces_total: int | None = Field(default=None, ge=0)
    attested_faces_active: int | None = Field(default=None, ge=0)
    attested_faces_revoked: int | None = Field(default=None, ge=0)
    attested_faces_promoted: int | None = Field(default=None, ge=0)
    inferred_ranges_live: int = Field(default=0, ge=0)
    inferred_ranges_total: int = Field(default=0, ge=0)


class WearableDeviceAssociationsOut(BaseModel):
    device_id: uuid.UUID
    tag_id: str
    teaching_held: bool
    open_hold: WearableTeachingHoldOut | None = None
    associations: list[WearableAssociationTaughtOut]


class WearableRevokeResponse(BaseModel):
    segment_id: str
    tag_id: str
    reason: Literal["swap_suspected", "operator"]
    actor: str
    already_revoked: bool
    gallery_rows_demoted: int = Field(ge=0)
    attested_faces_revoked: int | None = Field(default=None, ge=0)
    already_promoted_faces: list[PromotedAttestationOut] = Field(default_factory=list)
    inferred_ranges_compensated: int = Field(ge=0)
    hold: WearableTeachingHoldOut


class WearableResumeTeachingResponse(BaseModel):
    tag_id: str
    resumed: bool
    hold: WearableTeachingHoldOut | None = None
