"""Rename the per-camera face floor to say it is a raw similarity, and bound it.

The value was always compared with raw ArcFace cosine similarity, never with a calibrated
probability, so ``face_id_min_confidence`` becomes ``face_id_min_raw_similarity``. Existing values
are kept; the new check rejects anything outside [0, 1].

Revision ID: 0003_cts_camera_face_raw_similarity
Revises: 0002_medication_schedule
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_cts_camera_face_raw_similarity"
down_revision: str | Sequence[str] | None = "0002_medication_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "ck_cts_cameras_face_id_min_raw_similarity_range"


def upgrade() -> None:
    op.alter_column(
        "cts_cameras", "face_id_min_confidence", new_column_name="face_id_min_raw_similarity"
    )
    op.create_check_constraint(
        _CHECK,
        "cts_cameras",
        "face_id_min_raw_similarity IS NULL "
        "OR (face_id_min_raw_similarity >= 0 AND face_id_min_raw_similarity <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK, "cts_cameras", type_="check")
    op.alter_column(
        "cts_cameras", "face_id_min_raw_similarity", new_column_name="face_id_min_confidence"
    )
