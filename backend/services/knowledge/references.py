"""Reference lookups that guard knowledge deletes and image purges.

Rule pipeline steps point at info cards and quizzes through ``PipelineStep.config_json``, which
no foreign key can protect, so deletes check those references explicitly. Historical delivery,
session, and response rows are protected by ``ON DELETE RESTRICT`` foreign keys instead; the
services map that violation to a 409 rather than duplicating it as a read-then-write check.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.pipeline import PipelineStep


def rule_ids_referencing(
    db: Session, *, step_type: str, config_key: str, resource_id: int
) -> list[int]:
    """Ids of every rule (enabled or not) whose ``step_type`` step names ``resource_id``.

    Disabled rules count: deleting the resource would make the rule fail the next time a
    caregiver re-enables it. The id is compared as text so a step holding an empty or templated
    value cannot make the whole lookup fail on a cast.
    """
    rows = db.execute(
        select(PipelineStep.rule_id)
        .where(
            PipelineStep.step_type == step_type,
            PipelineStep.config_json[config_key].as_string() == str(resource_id),
        )
        .distinct()
        .order_by(PipelineStep.rule_id)
    ).scalars()
    return list(rows)


def owned_object_names(image_slot: Mapping[str, Any] | None, owner_prefix: str) -> set[str]:
    """MinIO object names recorded in ``image_slot`` that live under ``owner_prefix``.

    A slot bound to a knowledge-document image records that document's object as its original;
    it is shared with the document and must never be purged with the slot, so only names under
    the owning resource's own prefix are returned.
    """
    if not image_slot:
        return set()
    names: set[str] = set()
    original = image_slot.get("original_object_name")
    if isinstance(original, str) and original.startswith(owner_prefix):
        names.add(original)
    variants = image_slot.get("variants")
    if isinstance(variants, Mapping):
        for entry in variants.values():
            name = entry.get("object_name") if isinstance(entry, Mapping) else None
            if isinstance(name, str) and name.startswith(owner_prefix):
                names.add(name)
    return names


def names_in_use(slots: Iterable[Mapping[str, Any] | None], owner_prefix: str) -> set[str]:
    """Union of :func:`owned_object_names` across sibling slots that are being kept."""
    in_use: set[str] = set()
    for slot in slots:
        in_use |= owned_object_names(slot, owner_prefix)
    return in_use
