"""Service for fixed RF node (receiver and ranging anchor) placement and survey checks."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from cts_contracts import RangingTechnology, RfNodeRole
from sqlalchemy.exc import IntegrityError

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.wearable import RfNode
from backend.schemas.wearables import (
    RfNodeCreate,
    RfNodeListOut,
    RfNodeOut,
    RfNodeSurveyCheckItemOut,
    RfNodeSurveyCheckOut,
    RfNodeSurveyCheckRequest,
    RfNodeUpdate,
)
from backend.services.floor_plan_geometry import (
    SURVEY_DISCREPANCY_WARN_M,
    FloorPlanScale,
    evaluate_survey_distance,
    floor_plan_scale,
    norm_to_floor_m,
)
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

logger = get_logger(__name__)


def _node_out(
    node: RfNode,
    *,
    scale: FloorPlanScale | None,
    room_names: dict[int, str],
) -> RfNodeOut:
    x_m: float | None = None
    y_m: float | None = None
    if scale is not None:
        raw_x, raw_y = norm_to_floor_m(node.x_norm, node.y_norm, scale)
        x_m = round(raw_x, 4)
        y_m = round(raw_y, 4)
    return RfNodeOut(
        id=node.id,
        anchor_id=node.anchor_id,
        label=node.label,
        adapter_id=node.adapter_id,
        node_role=RfNodeRole(node.node_role),
        technology=RangingTechnology(node.technology),
        room_id=node.room_id,
        room_name=room_names.get(node.room_id) if node.room_id is not None else None,
        x_norm=node.x_norm,
        y_norm=node.y_norm,
        x_m=x_m,
        y_m=y_m,
        z_m=node.z_m,
        is_active=node.is_active,
        placement_residual_m=node.placement_residual_m,
        uwb_address_hex=node.uwb_address_hex,
        uwb_channel=node.uwb_channel,
        uwb_preamble_index=node.uwb_preamble_index,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


class RfNodeService:
    """CRUD and tape-distance survey validation for fixed RF nodes on the floor plan."""

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock

    def list_nodes(self, *, active_only: bool = False) -> RfNodeListOut:
        with self._repo.session() as db:
            settings = self._repo.get_household_settings(db)
            scale = floor_plan_scale(settings)
            nodes = self._repo.list_nodes(db, active_only=active_only)
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            items = [_node_out(n, scale=scale, room_names=room_names) for n in nodes]
            return RfNodeListOut(
                items=items,
                total=len(items),
                floor_plan_ready=scale is not None,
                floor_plan_id=scale.floor_plan_id if scale is not None else None,
                floor_width_m=round(scale.width_m, 4) if scale is not None else None,
                floor_height_m=round(scale.height_m, 4) if scale is not None else None,
            )

    def get_node(self, node_id: uuid.UUID) -> RfNodeOut:
        with self._repo.session() as db:
            node = self._repo.get_node(db, node_id)
            if node is None:
                raise NotFoundError("RfNode", str(node_id))
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            return _node_out(node, scale=scale, room_names=room_names)

    def create_node(self, payload: RfNodeCreate, *, actor: str) -> RfNodeOut:
        now = self._clock()
        with self._repo.session() as db:
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            if scale is None:
                raise ValidationError(
                    "Upload a household floor plan and set its measured scale before placing RF nodes"
                )
            if payload.room_id is not None and self._repo.get_room(db, payload.room_id) is None:
                raise NotFoundError("Room", payload.room_id)

            node = RfNode(
                id=uuid.uuid4(),
                anchor_id=payload.anchor_id,
                label=payload.label,
                adapter_id=payload.adapter_id,
                node_role=payload.node_role.value,
                technology=payload.technology.value,
                room_id=payload.room_id,
                x_norm=payload.x_norm,
                y_norm=payload.y_norm,
                z_m=payload.z_m,
                is_active=payload.is_active,
                placement_residual_m=payload.placement_residual_m,
                uwb_address_hex=payload.uwb_address_hex,
                uwb_channel=payload.uwb_channel,
                uwb_preamble_index=payload.uwb_preamble_index,
                created_at=now,
                updated_at=now,
            )
            db.add(node)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "An RF node with that anchor_id or active UWB short address already exists"
                ) from exc
            db.refresh(node)
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            logger.info(
                "rf_node_created",
                node_id=str(node.id),
                anchor_id=node.anchor_id,
                node_role=node.node_role,
                technology=node.technology,
                actor=actor,
            )
            return _node_out(node, scale=scale, room_names=room_names)

    def update_node(
        self,
        node_id: uuid.UUID,
        payload: RfNodeUpdate,
        *,
        actor: str,
    ) -> RfNodeOut:
        now = self._clock()
        with self._repo.session() as db:
            node = self._repo.get_node(db, node_id)
            if node is None:
                raise NotFoundError("RfNode", str(node_id))
            updates = payload.model_dump(exclude_unset=True)
            room_id_val = updates.get("room_id")
            if room_id_val is not None and self._repo.get_room(db, room_id_val) is None:
                raise NotFoundError("Room", room_id_val)
            for key, value in updates.items():
                if isinstance(value, (RfNodeRole, RangingTechnology)):
                    setattr(node, key, value.value)
                else:
                    setattr(node, key, value)
            if node.technology == RangingTechnology.UWB.value:
                if node.uwb_channel is None:
                    node.uwb_channel = 9
                if node.uwb_preamble_index is None:
                    node.uwb_preamble_index = 10
            node.updated_at = now
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "Updating RF node conflicts with an existing active UWB short address"
                ) from exc
            db.refresh(node)
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            room_names = {rid: r.name for rid, r in self._repo.list_rooms_map(db).items()}
            logger.info(
                "rf_node_updated",
                node_id=str(node.id),
                anchor_id=node.anchor_id,
                is_active=node.is_active,
                actor=actor,
            )
            return _node_out(node, scale=scale, room_names=room_names)

    def delete_node(self, node_id: uuid.UUID, *, actor: str) -> None:
        with self._repo.session() as db:
            node = self._repo.get_node(db, node_id)
            if node is None:
                raise NotFoundError("RfNode", str(node_id))
            anchor_id = node.anchor_id
            db.delete(node)
            db.commit()
            logger.info("rf_node_deleted", node_id=str(node_id), anchor_id=anchor_id, actor=actor)

    def survey_check(self, payload: RfNodeSurveyCheckRequest) -> RfNodeSurveyCheckOut:
        """Validate clicked floor-plan coordinates against tape distances to walls or nodes."""
        with self._repo.session() as db:
            scale = floor_plan_scale(self._repo.get_household_settings(db))
            if scale is None:
                raise ValidationError(
                    "Upload a household floor plan and set its measured scale before running a survey check"
                )
            x_m, y_m = norm_to_floor_m(payload.x_norm, payload.y_norm, scale)
            checks: list[RfNodeSurveyCheckItemOut] = []
            for item in payload.measurements:
                other_xyz: tuple[float, float, float] | None = None
                if item.reference_kind == "node":
                    ref_node = self._repo.get_node_by_anchor_id(db, item.reference_id)
                    if ref_node is None:
                        raise NotFoundError("RfNode", item.reference_id)
                    ox, oy = norm_to_floor_m(ref_node.x_norm, ref_node.y_norm, scale)
                    other_xyz = (ox, oy, ref_node.z_m)
                try:
                    checked = evaluate_survey_distance(
                        x_m=x_m,
                        y_m=y_m,
                        z_m=payload.z_m,
                        reference_kind=item.reference_kind,
                        reference_id=item.reference_id,
                        measured_m=item.measured_m,
                        scale=scale,
                        other_node_xyz_m=other_xyz,
                    )
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
                checks.append(
                    RfNodeSurveyCheckItemOut(
                        reference_kind=checked.reference_kind,
                        reference_id=checked.reference_id,
                        measured_m=checked.measured_m,
                        expected_m=checked.expected_m,
                        discrepancy_m=checked.discrepancy_m,
                        exceeds_tolerance=checked.exceeds_tolerance,
                    )
                )

            max_disc = max((c.discrepancy_m for c in checks), default=0.0)
            return RfNodeSurveyCheckOut(
                x_m=round(x_m, 4),
                y_m=round(y_m, 4),
                z_m=payload.z_m,
                tolerance_m=SURVEY_DISCREPANCY_WARN_M,
                max_discrepancy_m=round(max_disc, 4),
                warning=any(c.exceeds_tolerance for c in checks),
                checks=checks,
            )
