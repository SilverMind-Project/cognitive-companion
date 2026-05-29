"""Consolidated baseline schema for cognitive-companion.

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-05-28

Squashes all 21 incremental migrations into a single baseline representing
the final schema state. downgrade() is intentionally a no-op; this is a
dev-stage app where rollbacks are not required.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

import backend.core.time
from alembic import op

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Extensions -----------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")

    # -- conversation_sessions ------------------------------------------------
    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- rooms ----------------------------------------------------------------
    # Created early: many tables reference rooms.id via FK.
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ha_area_id", sa.String(length=128), nullable=True),
        sa.Column("floor", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Added by 0010_floor_plan_and_room_polygons
        sa.Column("floor_polygon", sa.JSON(), nullable=True),
        # Added by 0017_calibration_health_and_transit_zones
        sa.Column("has_camera", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("inferred_dwell_alert_minutes", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rooms_name"), "rooms", ["name"], unique=True)

    # -- household_members ----------------------------------------------------
    op.create_table(
        "household_members",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_guest", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", backend.core.time.UTCDateTime(), nullable=True),
        # Added by 0009_alert_suppressions_and_priority
        sa.Column("alert_priority", sa.Integer(), nullable=False, server_default="5"),
        # Added by 0012_cts_alert_config
        sa.Column("cts_alert_config", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- cts_cameras ----------------------------------------------------------
    # Reflects final state after 0003, 0007, 0008, 0015, 0016, 0017.
    # Column "location" was renamed to "room_name" in 0007.
    # room_id FK to rooms is added after rooms table exists (below).
    op.create_table(
        "cts_cameras",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("rtsp_url", sa.String(length=1024), nullable=False),
        # "location" was renamed to "room_name" in 0007_cts_camera_room_linkage
        sa.Column("room_name", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("face_id_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("face_id_min_confidence", sa.Float(), nullable=True),
        sa.Column("floor_plan_key", sa.String(length=512), nullable=True),
        sa.Column("homography", sa.JSON(), nullable=True),
        sa.Column("homography_residuals", sa.JSON(), nullable=True),
        sa.Column("privacy_zones", sa.JSON(), nullable=True),
        sa.Column("health_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Added by 0003_cts_camera_rotation
        sa.Column("rotation_degrees", sa.Integer(), nullable=False, server_default="0"),
        # Added by 0007_cts_camera_room_linkage
        sa.Column("room_id", sa.Integer(), nullable=True),
        # Added by 0008_cts_camera_role_and_overlap
        sa.Column("role", sa.String(32), nullable=False, server_default="surveillance"),
        # Added by 0015_cts_camera_physical
        sa.Column("horizontal_fov_deg", sa.Float(), nullable=True),
        sa.Column("mounting_height_m", sa.Float(), nullable=True),
        sa.Column("tilt_deg", sa.Float(), nullable=True),
        sa.Column("snapshot_width", sa.Integer(), nullable=True),
        sa.Column("snapshot_height", sa.Integer(), nullable=True),
        # Added by 0016_cts_camera_visibility
        sa.Column("visibility_polygon", JSONB, nullable=True),
        # Added by 0017_calibration_health_and_transit_zones
        sa.Column("homography_matrix", JSONB, nullable=True),
        sa.Column("homography_residual_m", sa.Float(), nullable=True),
        sa.Column("homography_method", sa.String(32), nullable=True),
        sa.Column("homography_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frame_natural_width", sa.Integer(), nullable=True),
        sa.Column("frame_natural_height", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "rotation_degrees IN (0, 90, 180, 270)",
            name="ck_cts_cameras_rotation",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cts_cameras_name"), "cts_cameras", ["name"], unique=False)
    op.create_index("ix_cts_cameras_room_id", "cts_cameras", ["room_id"])
    # FK added after rooms table is created
    op.create_foreign_key(
        "fk_cts_cameras_room_id", "cts_cameras", "rooms", ["room_id"], ["id"]
    )

    # -- cts_dementia_signals -------------------------------------------------
    # Reflects final state after 0004 (signal_id, algorithm_version added).
    op.create_table(
        "cts_dementia_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("window_start", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("window_end", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("baseline", sa.Float(), nullable=True),
        sa.Column("z_score", sa.Float(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("acknowledged_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "received_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Added by 0004_cts_signal_id_algo_version
        sa.Column("signal_id", sa.String(64), nullable=True),
        sa.Column("algorithm_version", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cts_dementia_signals_person_id"),
        "cts_dementia_signals",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cts_dementia_signals_severity"),
        "cts_dementia_signals",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cts_dementia_signals_signal_type"),
        "cts_dementia_signals",
        ["signal_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cts_dementia_signals_window_end"),
        "cts_dementia_signals",
        ["window_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cts_dementia_signals_window_start"),
        "cts_dementia_signals",
        ["window_start"],
        unique=False,
    )
    op.create_index(
        "ix_cts_dementia_signals_signal_id",
        "cts_dementia_signals",
        ["signal_id"],
    )

    # -- emergency_alerts -----------------------------------------------------
    op.create_table(
        "emergency_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sensor_id", sa.String(length=128), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("assistance_needed", sa.Boolean(), nullable=False),
        sa.Column("notification_sent_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- rules ----------------------------------------------------------------
    # trigger_types is JSONB (altered in 0013_trigger_types_jsonb).
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "trigger_types",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"sensor_event\"]'"),
        ),
        sa.Column("primary_sensor_id", sa.String(length=128), nullable=True),
        sa.Column("webhook_config", sa.JSON(), nullable=True),
        sa.Column("occupancy_config", sa.JSON(), nullable=True),
        sa.Column("telegram_trigger_config", sa.JSON(), nullable=True),
        sa.Column("cool_off_minutes", sa.Integer(), nullable=False),
        sa.Column("max_daily_triggers", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_executions", sa.Integer(), nullable=False),
        sa.Column("execution_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rules_name"), "rules", ["name"], unique=True)

    # -- cron_triggers --------------------------------------------------------
    op.create_table(
        "cron_triggers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("expression", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- rule_cron_triggers ---------------------------------------------------
    op.create_table(
        "rule_cron_triggers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column(
            "cron_trigger_id", sa.Integer(), sa.ForeignKey("cron_triggers.id"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_cron_triggers_rule_id", "rule_cron_triggers", ["rule_id"])
    op.create_index(
        "ix_rule_cron_triggers_cron_trigger_id", "rule_cron_triggers", ["cron_trigger_id"]
    )

    # -- cts_window_triggers --------------------------------------------------
    op.create_table(
        "cts_window_triggers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("window_seconds", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("min_detections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("min_identities", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cameras", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rooms", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("cooldown_seconds", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # -- rule_cts_window_triggers ---------------------------------------------
    op.create_table(
        "rule_cts_window_triggers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cts_window_trigger_id",
            sa.String(36),
            sa.ForeignKey("cts_window_triggers.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_rule_cts_window_triggers_rule_id",
        "rule_cts_window_triggers",
        ["rule_id"],
    )
    op.create_index(
        "ix_rule_cts_window_triggers_ct_id",
        "rule_cts_window_triggers",
        ["cts_window_trigger_id"],
    )

    # -- pipeline_steps -------------------------------------------------------
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_step_on_true", sa.Integer(), nullable=True),
        sa.Column("next_step_on_false", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["next_step_on_false"], ["pipeline_steps.id"]),
        sa.ForeignKeyConstraint(["next_step_on_true"], ["pipeline_steps.id"]),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_steps_rule_id"), "pipeline_steps", ["rule_id"], unique=False
    )

    # -- workflow_executions --------------------------------------------------
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("event_log_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_data_json", sa.JSON(), nullable=False),
        sa.Column(
            "started_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resume_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["current_step_id"], ["pipeline_steps.id"]),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_executions_rule_id"), "workflow_executions", ["rule_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_executions_status"), "workflow_executions", ["status"], unique=False
    )

    # -- event_logs -----------------------------------------------------------
    # Depends on rules + workflow_executions.
    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("rule_name", sa.String(length=256), nullable=True),
        sa.Column("sensor_id", sa.String(length=128), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("media_paths_json", sa.JSON(), nullable=True),
        sa.Column("pipeline_data_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workflow_execution_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"]),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_event_logs_rule_name"), "event_logs", ["rule_name"], unique=False)
    op.create_index(
        "ix_event_logs_rule_status_ts",
        "event_logs",
        ["rule_id", "status", "timestamp"],
        unique=False,
    )
    op.create_index(op.f("ix_event_logs_status"), "event_logs", ["status"], unique=False)
    op.create_index(op.f("ix_event_logs_timestamp"), "event_logs", ["timestamp"], unique=False)

    # Add FK from workflow_executions to event_logs (circular reference resolved after both tables exist)
    op.create_foreign_key(None, "workflow_executions", "event_logs", ["event_log_id"], ["id"])

    # -- image_templates ------------------------------------------------------
    op.create_table(
        "image_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("image_filename", sa.String(length=256), nullable=False),
        sa.Column("font_filename", sa.String(length=256), nullable=False),
        sa.Column("regions_json", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_templates_name"), "image_templates", ["name"], unique=True)

    # -- active_image_state ---------------------------------------------------
    op.create_table(
        "active_image_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sensor_id", sa.String(length=128), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("rendered_text", sa.Text(), nullable=True),
        sa.Column("expires_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_served_hash", sa.String(length=64), nullable=True),
        sa.Column("last_served_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["image_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_active_image_state_sensor_id"), "active_image_state", ["sensor_id"], unique=True
    )

    # -- activity_sessions ----------------------------------------------------
    op.create_table(
        "activity_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column("opened_at", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("closed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("timeout_minutes", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("open_event_id", sa.Integer(), nullable=True),
        sa.Column("close_event_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["close_event_id"], ["event_logs.id"]),
        sa.ForeignKeyConstraint(["open_event_id"], ["event_logs.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activity_sessions_activity_type"),
        "activity_sessions",
        ["activity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_sessions_observation_id"),
        "activity_sessions",
        ["observation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_sessions_opened_at"), "activity_sessions", ["opened_at"], unique=False
    )
    op.create_index(
        op.f("ix_activity_sessions_person_id"), "activity_sessions", ["person_id"], unique=False
    )

    # -- conversation_turns ---------------------------------------------------
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- daily_reports --------------------------------------------------------
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("report_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("generated_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("sleep_total_minutes", sa.Integer(), nullable=True),
        sa.Column("sleep_quality_score", sa.Float(), nullable=True),
        sa.Column("sleep_disruptions", sa.Integer(), nullable=True),
        sa.Column("meal_prep_count", sa.Integer(), nullable=True),
        sa.Column("meal_eating_count", sa.Integer(), nullable=True),
        sa.Column("meal_avg_duration_minutes", sa.Float(), nullable=True),
        sa.Column("medication_doses_taken", sa.Integer(), nullable=True),
        sa.Column("medication_doses_due", sa.Integer(), nullable=True),
        sa.Column("medication_adherence_pct", sa.Float(), nullable=True),
        sa.Column("bathroom_visit_count", sa.Integer(), nullable=True),
        sa.Column("bathroom_total_minutes", sa.Integer(), nullable=True),
        sa.Column("bathroom_avg_duration_minutes", sa.Float(), nullable=True),
        sa.Column("door_open_count", sa.Integer(), nullable=True),
        sa.Column("door_close_count", sa.Integer(), nullable=True),
        sa.Column("exercise_session_count", sa.Integer(), nullable=True),
        sa.Column("exercise_total_minutes", sa.Integer(), nullable=True),
        sa.Column("room_time_json", sa.JSON(), nullable=True),
        sa.Column("summary_text", sa.String(length=4096), nullable=True),
        sa.Column("summary_created_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("wellness_score", sa.Float(), nullable=True),
        sa.Column("wellness_alerts_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "report_date", name="uix_person_date"),
    )
    op.create_index(
        op.f("ix_daily_reports_person_id"), "daily_reports", ["person_id"], unique=False
    )

    # -- person_activities ----------------------------------------------------
    op.create_table(
        "person_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column(
            "detected_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_event_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["event_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_activities_activity_type"),
        "person_activities",
        ["activity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_activities_detected_at"), "person_activities", ["detected_at"], unique=False
    )
    op.create_index(
        op.f("ix_person_activities_observation_id"),
        "person_activities",
        ["observation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_activities_person_id"), "person_activities", ["person_id"], unique=False
    )
    op.create_index(
        op.f("ix_person_activities_session_id"), "person_activities", ["session_id"], unique=False
    )

    # -- person_location_history ----------------------------------------------
    # Retained: superseded by presence_segments but still read by legacy presence providers.
    op.create_table(
        "person_location_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column("entered_at", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("exited_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("direction_semantic", sa.String(length=32), nullable=True),
        sa.Column("from_room_id", sa.Integer(), nullable=True),
        sa.Column("from_room_name", sa.String(length=128), nullable=True),
        sa.Column("superseded_by_revision_id", sa.String(length=64), nullable=True),
        sa.Column("global_track_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["from_room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_location_history_entered_at"),
        "person_location_history",
        ["entered_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_location_history_global_track_id"),
        "person_location_history",
        ["global_track_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_location_history_person_id"),
        "person_location_history",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_location_history_superseded_by_revision_id"),
        "person_location_history",
        ["superseded_by_revision_id"],
        unique=False,
    )

    # -- person_location_state ------------------------------------------------
    # Retained: superseded by presence_segments but still read by legacy presence providers.
    op.create_table(
        "person_location_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("current_room_id", sa.Integer(), nullable=True),
        sa.Column("current_room_name", sa.String(length=128), nullable=True),
        sa.Column("last_seen_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("last_sensor_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["current_room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_location_state_person_id"),
        "person_location_state",
        ["person_id"],
        unique=True,
    )

    # -- person_sightings -----------------------------------------------------
    op.create_table(
        "person_sightings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("sensor_id", sa.String(length=128), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("room_name", sa.String(length=128), nullable=True),
        sa.Column(
            "timestamp",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=True),
        sa.Column("bbox_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_person_sightings_person_id"), "person_sightings", ["person_id"], unique=False
    )
    op.create_index(
        op.f("ix_person_sightings_sensor_id"), "person_sightings", ["sensor_id"], unique=False
    )
    op.create_index(
        op.f("ix_person_sightings_timestamp"), "person_sightings", ["timestamp"], unique=False
    )

    # -- rule_contexts --------------------------------------------------------
    op.create_table(
        "rule_contexts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("context_type", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("negate", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- rule_dependencies ----------------------------------------------------
    op.create_table(
        "rule_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dependent_rule_id", sa.Integer(), nullable=False),
        sa.Column("parent_rule_id", sa.Integer(), nullable=False),
        sa.Column("lookback_minutes", sa.Integer(), nullable=False),
        sa.Column("require_success", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["dependent_rule_id"], ["rules.id"]),
        sa.ForeignKeyConstraint(["parent_rule_id"], ["rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- sensors --------------------------------------------------------------
    op.create_table(
        "sensors",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("sensor_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("ha_entity_id", sa.String(length=256), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sensors_name"), "sensors", ["name"], unique=False)

    # -- interactive_responses ------------------------------------------------
    op.create_table(
        "interactive_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("timestamp", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("raw_response_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
        sa.ForeignKeyConstraint(["step_id"], ["pipeline_steps.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_interactive_responses_created_at"),
        "interactive_responses",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_interactive_responses_execution_id"),
        "interactive_responses",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_interactive_responses_execution_step",
        "interactive_responses",
        ["execution_id", "step_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_interactive_responses_step_id"),
        "interactive_responses",
        ["step_id"],
        unique=False,
    )

    # -- media_cache ----------------------------------------------------------
    op.create_table(
        "media_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("object_name", sa.String(length=512), nullable=False),
        sa.Column("presigned_url", sa.Text(), nullable=True),
        sa.Column("sensor_id", sa.String(length=128), nullable=True),
        sa.Column(
            "captured_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", backend.core.time.UTCDateTime(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_media_cache_captured_at"), "media_cache", ["captured_at"], unique=False
    )
    op.create_index(
        op.f("ix_media_cache_expires_at"), "media_cache", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_media_cache_object_name"), "media_cache", ["object_name"], unique=True
    )
    op.create_index(
        op.f("ix_media_cache_sensor_id"), "media_cache", ["sensor_id"], unique=False
    )

    # -- knowledge_documents --------------------------------------------------
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="uploaded", nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded','chunked','approved','archived')",
            name="ck_knowledge_documents_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- knowledge_document_images --------------------------------------------
    op.create_table(
        "knowledge_document_images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("minio_object_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.Text(), server_default="", nullable=False),
        sa.Column("ord", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- knowledge_document_chunks --------------------------------------------
    op.create_table(
        "knowledge_document_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_kdc_doc_chunk"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_cards -----------------------------------------------------------
    op.create_table(
        "info_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("layout_id", sa.Text(), server_default="text_only", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("voice_instruction", sa.Text(), server_default="", nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_info_cards_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_card_image_slots ------------------------------------------------
    op.create_table(
        "info_card_image_slots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "info_card_id",
            sa.BigInteger(),
            sa.ForeignKey("info_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column(
            "source_image_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_document_images.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_object_name", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), server_default="", nullable=False),
        sa.Column("variants", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.UniqueConstraint("info_card_id", "slot_index", name="uq_icis_card_slot"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quizzes --------------------------------------------------------------
    op.create_table(
        "quizzes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "question_layout_id",
            sa.Text(),
            server_default="quiz_with_optional_image",
            nullable=False,
        ),
        sa.Column("intro_voice_template", sa.Text(), server_default="", nullable=False),
        sa.Column("voice_instruction", sa.Text(), server_default="", nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_quizzes_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_questions -------------------------------------------------------
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "quiz_id",
            sa.BigInteger(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("choices", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("expected_answer", sa.Text(), server_default="", nullable=False),
        sa.Column("explanation", sa.Text(), server_default="", nullable=False),
        sa.Column("image_slot", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'open_ended')",
            name="ck_quiz_questions_type",
        ),
        sa.UniqueConstraint("quiz_id", "ord", name="uq_qq_quiz_ord"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_sessions --------------------------------------------------------
    # Includes question_order column added by 990462f4cf44_.
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "quiz_id",
            sa.BigInteger(),
            sa.ForeignKey("quizzes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_id",
            sa.BigInteger(),
            sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("senior_id", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="started", nullable=False),
        sa.Column("current_question_ord", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "started_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", backend.core.time.UTCDateTime(), nullable=True),
        # Added by 990462f4cf44_
        sa.Column(
            "question_order",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('started','in_progress','completed','abandoned','timed_out')",
            name="ck_quiz_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_responses -------------------------------------------------------
    op.create_table(
        "quiz_responses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.BigInteger(),
            sa.ForeignKey("quiz_questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("question_ord", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("chosen_choice_id", sa.Text(), nullable=True),
        sa.Column("chosen_choice_text", sa.Text(), nullable=True),
        sa.Column("open_ended_text", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "answered_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint("session_id", "question_id", name="uq_qr_session_question"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_card_deliveries -------------------------------------------------
    op.create_table(
        "info_card_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "info_card_id",
            sa.BigInteger(),
            sa.ForeignKey("info_cards.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_id",
            sa.BigInteger(),
            sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channels", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "delivered_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("viewed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("dismissed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("dismissed_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- senior_knowledge_queries ---------------------------------------------
    op.create_table(
        "senior_knowledge_queries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "asked_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("senior_id", sa.Text(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "source_document_ids", sa.ARRAY(sa.Integer()), server_default="{}", nullable=False
        ),
        sa.Column(
            "source_chunk_ids", sa.ARRAY(sa.Integer()), server_default="{}", nullable=False
        ),
        sa.Column("top_similarity", sa.Float(), nullable=True),
        sa.Column("answered_via", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- cts_identity_revision_log --------------------------------------------
    op.create_table(
        "cts_identity_revision_log",
        sa.Column("revision_id", sa.String(128), primary_key=True),
        sa.Column("global_track_id", sa.String(128), nullable=False),
        sa.Column("previous_identity_id", sa.String(128), nullable=True),
        sa.Column("new_identity_id", sa.String(128), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("rewritten_rows", sa.Integer(), default=0),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_cts_identity_revision_log_applied_at",
        "cts_identity_revision_log",
        [sa.text("applied_at DESC")],
    )
    op.create_index(
        "ix_cts_identity_revision_log_gt_applied",
        "cts_identity_revision_log",
        ["global_track_id", sa.text("applied_at DESC")],
    )
    op.create_index(
        "ix_cts_identity_revision_log_kind_applied",
        "cts_identity_revision_log",
        ["kind", sa.text("applied_at DESC")],
    )

    # -- cts_camera_overlap_groups --------------------------------------------
    op.create_table(
        "cts_camera_overlap_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("camera_ids", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -- cts_alert_suppressions -----------------------------------------------
    op.create_table(
        "cts_alert_suppressions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "person_id",
            sa.String(64),
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("signal_kind", sa.String(64), nullable=True),
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_alert_suppressions_person_until",
        "cts_alert_suppressions",
        ["person_id", "suppressed_until"],
    )

    # -- household_settings ---------------------------------------------------
    # Singleton table (CHECK id = 1). Includes cts_adjacency_edges from 0011.
    op.create_table(
        "household_settings",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("floor_plan_key", sa.String(512), nullable=True),
        sa.Column("floor_plan_width", sa.Integer(), nullable=True),
        sa.Column("floor_plan_height", sa.Integer(), nullable=True),
        sa.Column("floor_meters_per_pixel", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Added by 0011_cts_adjacency_edges
        sa.Column("cts_adjacency_edges", sa.JSON(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_household_settings_singleton"),
    )

    # -- room_occupancy_state -------------------------------------------------
    op.create_table(
        "room_occupancy_state",
        sa.Column("room_name", sa.String(128), primary_key=True),
        sa.Column("occupied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("person_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # -- transit_zones --------------------------------------------------------
    op.create_table(
        "transit_zones",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="door"),
        sa.Column("polygon", JSONB, nullable=False),
        sa.Column("inside_room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("outside_room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("direction_vec", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # -- location_observations ------------------------------------------------
    # TimescaleDB hypertable partitioned on observed_at.
    # Composite PK (id, observed_at) required by TimescaleDB uniqueness rules.
    op.create_table(
        "location_observations",
        sa.Column("id", UUID, nullable=False),
        sa.Column(
            "person_id",
            sa.String(64),
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("floor_x_m", sa.Float(), nullable=True),
        sa.Column("floor_y_m", sa.Float(), nullable=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id", "observed_at", name="location_observations_pkey"),
    )
    op.execute(
        "SELECT create_hypertable('location_observations', 'observed_at', "
        "chunk_time_interval => INTERVAL '6 hours', if_not_exists => TRUE)"
    )
    op.create_index(
        "idx_loc_obs_person",
        "location_observations",
        ["person_id", sa.text("observed_at DESC")],
    )
    op.create_index(
        "idx_loc_obs_room",
        "location_observations",
        ["room_id", sa.text("observed_at DESC")],
    )

    # -- presence_segments ----------------------------------------------------
    op.create_table(
        "presence_segments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "person_id",
            sa.String(64),
            sa.ForeignKey("household_members.id"),
            nullable=False,
        ),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_source", sa.String(32), nullable=False),
        sa.Column("exit_source", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by", UUID, sa.ForeignKey("presence_segments.id"), nullable=True
        ),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "idx_ps_person_open",
        "presence_segments",
        ["person_id"],
        postgresql_where=sa.text("exited_at IS NULL"),
    )
    op.create_index(
        "idx_ps_person_time",
        "presence_segments",
        ["person_id", sa.text("entered_at DESC")],
    )
    op.create_index(
        "idx_ps_room_time",
        "presence_segments",
        ["room_id", sa.text("entered_at DESC")],
    )

    # -- Knowledge indices ----------------------------------------------------
    op.create_index(
        "idx_senior_kq_asked_at", "senior_knowledge_queries", ["asked_at"], unique=False
    )
    op.create_index("idx_quiz_sessions_started_at", "quiz_sessions", ["started_at"], unique=False)
    op.create_index(
        "idx_info_deliveries_at", "info_card_deliveries", ["delivered_at"], unique=False
    )

    # Vector similarity search index (pgvectorscale StreamingDiskANN).
    # The primary RAG query uses ORDER BY kdc.embedding <=> :vec (cosine distance).
    op.execute(
        "CREATE INDEX idx_kdc_embedding ON knowledge_document_chunks "
        "USING diskann (embedding vector_cosine_ops)"
    )
    op.create_index(
        "idx_knowledge_documents_status", "knowledge_documents", ["status"], unique=False
    )

    # -- Seed data: info_card image template ----------------------------------
    op.execute(
        sa.text(
            """INSERT INTO image_templates (name, description, width, height, image_filename, font_filename, regions_json, is_default)
               VALUES (
                   'info_card',
                   'Info card display (title + image + body)',
                   800, 480,
                   'info_card_bg.png',
                   'NotoSansTamil-Regular.ttf',
                   :regions,
                   false
               )"""
        ).bindparams(
            sa.bindparam(
                "regions",
                value=[
                    {
                        "name": "title",
                        "x": 20,
                        "y": 10,
                        "width": 760,
                        "height": 50,
                        "font_size_max": 28,
                        "font_size_min": 14,
                        "align": "center",
                        "bg_color": [0, 0, 0, 160],
                        "text_color": [255, 255, 255, 255],
                        "multiline": True,
                    },
                    {
                        "name": "image",
                        "x": 20,
                        "y": 70,
                        "width": 760,
                        "height": 260,
                        "type": "image",
                    },
                    {
                        "name": "body",
                        "x": 20,
                        "y": 340,
                        "width": 760,
                        "height": 130,
                        "font_size_max": 18,
                        "font_size_min": 10,
                        "align": "left",
                        "bg_color": [0, 0, 0, 0],
                        "text_color": [0, 0, 0, 255],
                        "multiline": True,
                    },
                ],
                type_=JSONB(),
            )
        )
    )


def downgrade() -> None:
    pass
