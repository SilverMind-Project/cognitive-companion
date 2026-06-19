from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.guided_task import Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.scripts.backfill_gate_graphs import backfill_gate_graphs


def _seed_steps(db_session: Session):
    member = db_session.get(HouseholdMember, "resident-1")
    if not member:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()

    routine = Routine(name="Test Routine", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()

    # Step 0: Needs backfill
    step0 = RoutineStep(
        routine_id=routine.id,
        ord=0,
        prompt_template="Step 0 prompt",
        completion_gate={"kinds": ["response", "vision_confirm"], "vision": {"confirm": {}}},
        is_safety_critical=False,
    )
    # Step 1: Already has gate_graph_rule_id
    step1 = RoutineStep(
        routine_id=routine.id,
        ord=1,
        prompt_template="Step 1 prompt",
        completion_gate={
            "kinds": ["response", "vision_confirm"],
            "vision": {"gate_graph_rule_id": 999, "confirm": {}},
        },
        is_safety_critical=False,
    )
    # Step 2: Non-vision step
    step2 = RoutineStep(
        routine_id=routine.id,
        ord=2,
        prompt_template="Step 2 prompt",
        completion_gate={"kinds": ["response"]},
        is_safety_critical=False,
    )
    db_session.add_all([step0, step1, step2])
    db_session.commit()
    return step0.id, step1.id, step2.id


def test_backfills_missing_gate_graph(db_session: Session) -> None:
    # Seed steps
    step0_id, step1_id, step2_id = _seed_steps(db_session)

    # Run backfill script function passing the db_session
    backfill_gate_graphs(db_session)

    # Query steps to check results (we use a fresh read)
    db_session.expire_all()

    s0 = db_session.get(RoutineStep, step0_id)
    s1 = db_session.get(RoutineStep, step1_id)
    s2 = db_session.get(RoutineStep, step2_id)

    # Step 0 should have been backfilled with a gate graph rule ID
    assert s0.completion_gate["vision"]["gate_graph_rule_id"] is not None
    assert s0.completion_gate["vision"]["gate_graph_rule_id"] > 0
    assert "confirm" in s0.completion_gate["vision"]

    # Step 1 should be untouched (gate_graph_rule_id stays 999)
    assert s1.completion_gate["vision"]["gate_graph_rule_id"] == 999

    # Step 2 should be untouched
    assert s2.completion_gate["kinds"] == ["response"]
    assert "vision" not in s2.completion_gate
