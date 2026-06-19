#!/usr/bin/env python3
"""Idempotent script to backfill default VLM gate graphs for steps using vision_confirm."""

import sys
from sqlalchemy.orm import Session
from backend.core.database import get_session
from backend.models.guided_task import RoutineStep
from backend.services.guided_task.gate_presets import build_default_vlm_gate
from backend.core.logging import get_logger

logger = get_logger(__name__)


def backfill_gate_graphs(db: Session | None = None) -> None:
    if db is not None:
        _run_backfill(db)
    else:
        db_session = get_session()
        try:
            _run_backfill(db_session)
        except Exception as e:
            logger.exception("backfill_failed", error=str(e))
            db_session.rollback()
            sys.exit(1)
        finally:
            db_session.close()


def _run_backfill(db: Session) -> None:
    steps = db.query(RoutineStep).all()
    backfilled_count = 0
    skipped_count = 0
    non_vision_count = 0

    for step in steps:
        gate = step.completion_gate or {}
        kinds = gate.get("kinds") or []
        if "vision_confirm" not in kinds:
            non_vision_count += 1
            continue

        vision_cfg = gate.get("vision") or gate.get("vision_confirm") or {}
        if vision_cfg.get("gate_graph_rule_id"):
            skipped_count += 1
            continue

        # Need to backfill
        logger.info(
            "backfilling_gate_graph_for_step",
            step_id=step.id,
            step_ord=step.ord,
            routine_id=step.routine_id,
        )

        # Build name and done description for the default gate
        rule_name = f"VLM confirm gate step {step.id} ord {step.ord}"
        done_desc = vision_cfg.get("done_description") or vision_cfg.get("description")

        rule = build_default_vlm_gate(
            db,
            name=rule_name,
            done_description=done_desc,
            model_id=vision_cfg.get("model_id"),
        )

        # Construct new shape
        confirm = vision_cfg.get("confirm") or {}
        confirm_new = {
            "window_s": confirm.get("window_s") or vision_cfg.get("window_s"),
            "max_frames": confirm.get("max_frames") or vision_cfg.get("max_frames"),
            "min_confidence": confirm.get("min_confidence") or vision_cfg.get("min_confidence"),
            "min_interval_s": confirm.get("min_interval_s") or vision_cfg.get("min_interval_s"),
            "model_id": confirm.get("model_id") or vision_cfg.get("model_id"),
            "on_max_disagreements": confirm.get("on_max_disagreements") or vision_cfg.get("on_max_disagreements"),
        }

        watch = vision_cfg.get("watch") or {}
        watch_new = {
            "enabled": watch.get("enabled", False),
            "tick_s": watch.get("tick_s"),
            "window_s": watch.get("window_s"),
            "max_frames": watch.get("max_frames"),
            "model_id": watch.get("model_id"),
            "auto_advance": watch.get("auto_advance", False),
            "auto_advance_k": watch.get("auto_advance_k"),
        }

        new_gate = dict(gate)
        new_gate["vision"] = {
            "gate_graph_rule_id": rule.id,
            "confirm": confirm_new,
            "watch": watch_new,
        }
        if "vision_confirm" in new_gate:
            new_gate.pop("vision_confirm", None)

        # Assign back and write to DB
        step.completion_gate = new_gate
        db.add(step)
        db.commit()
        backfilled_count += 1

    logger.info(
        "backfill_completed",
        backfilled=backfilled_count,
        skipped=skipped_count,
        non_vision=non_vision_count,
    )


if __name__ == "__main__":
    backfill_gate_graphs()
