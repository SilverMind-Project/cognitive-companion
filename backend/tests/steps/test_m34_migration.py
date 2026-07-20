import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule


def test_m34_migration_removes_cts_window(db_session):
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "6dd44f55f21e_remove_cts_window_from_pipeline_step_.py"
    )
    spec = importlib.util.spec_from_file_location("m34_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    db_session.execute(text("DELETE FROM pipeline_steps"))
    db_session.execute(text("DELETE FROM rules"))

    rule = Rule(name="dummy_rule")
    db_session.add(rule)
    db_session.commit()
    rule_id = rule.id

    seeds = [
        # cts_window with default path
        {
            "id": 1,
            "step_type": "scene_analysis",
            "config_json": {
                "image_source": "cts_window",
                "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
                "foo": "bar",
            },
        },
        # cts_window with custom path
        {
            "id": 2,
            "step_type": "image_crop",
            "config_json": {
                "image_source": "cts_window",
                "cts_frames_path": "custom.path.frames",
                "foo": "bar",
            },
        },
        # media_window with stray cts_frames_path key
        {
            "id": 3,
            "step_type": "person_identification",
            "config_json": {
                "image_source": "media_window",
                "cts_frames_path": "some.stray.path",
                "foo": "bar",
            },
        },
        # already-clean
        {
            "id": 4,
            "step_type": "llm_call",
            "config_json": {
                "image_source": "trigger",
                "pipeline_image_path": "prior.step",
                "foo": "bar",
            },
        },
    ]

    for s in seeds:
        step = PipelineStep(
            id=s["id"],
            rule_id=rule_id,
            step_type=s["step_type"],
            config_json=s["config_json"],
            order=s["id"],
        )
        db_session.add(step)
    db_session.commit()

    conn = db_session.connection()
    # patch the module op inside the loaded module
    with patch.object(module.op, "get_bind", return_value=conn):
        module.upgrade()

    db_session.commit()

    rows = db_session.execute(
        text("SELECT id, config_json FROM pipeline_steps ORDER BY id")
    ).fetchall()
    results = {}
    for r in rows:
        conf = r.config_json
        if isinstance(conf, str):
            conf = json.loads(conf)
        results[r.id] = conf

    # step_1: image_source becomes media_window, cts_frames_path deleted
    assert results[1]["image_source"] == "media_window"
    assert "cts_frames_path" not in results[1]
    assert "pipeline_image_path" not in results[1]

    # step_2: image_source becomes pipeline, pipeline_image_path = custom.path, cts_frames_path deleted
    assert results[2]["image_source"] == "pipeline"
    assert results[2]["pipeline_image_path"] == "custom.path.frames"
    assert "cts_frames_path" not in results[2]

    # step_3: stray path moves to pipeline_image_path, image_source = pipeline
    assert results[3]["image_source"] == "pipeline"
    assert results[3]["pipeline_image_path"] == "some.stray.path"
    assert "cts_frames_path" not in results[3]

    # step_4: unchanged
    assert results[4]["image_source"] == "trigger"
    assert results[4]["pipeline_image_path"] == "prior.step"
    assert "cts_frames_path" not in results[4]
