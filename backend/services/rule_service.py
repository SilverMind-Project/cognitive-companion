"""Shared rule-query service.

Single source for selecting rules and loading a rule with its graph, so the
rules router and the gate-graph router never write parallel queries (the
single-service-layer rule, CLAUDE.md). Callable rules (gate graphs) are
``trigger_types == []``; ``Rule.filter_callable`` / ``Rule.filter_active``
encode that split.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from backend.models.rule import Rule


def list_rules(db: Session, *, callable_only: bool | None = None) -> list[Rule]:
    """Return rules ordered by name.

    ``callable_only=True`` returns only callable (gate-graph) rules;
    ``False`` or ``None`` returns only active (triggerable) rules, matching the
    historical default of the rules list endpoint.
    """
    query = db.query(Rule)
    if callable_only is True:
        query = query.filter(Rule.filter_callable())
    else:
        query = query.filter(Rule.filter_active())
    return query.order_by(Rule.name).all()


def get_rule(db: Session, rule_id: int) -> Rule | None:
    """Load a rule with its steps, contexts, dependencies, and cron triggers."""
    return (
        db.query(Rule)
        .options(
            joinedload(Rule.steps),
            joinedload(Rule.contexts),
            joinedload(Rule.dependencies),
            joinedload(Rule.cron_triggers),
        )
        .filter(Rule.id == rule_id)
        .first()
    )
