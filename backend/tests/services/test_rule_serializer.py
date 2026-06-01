"""Tests for rule serialization/deserialization."""

from datetime import UTC, datetime

from backend.schemas.rule_bundle import (
    CronExpressionRef,
    RuleBundle,
    RuleDefinition,
    SourceInfo,
    StepBundle,
)
from backend.services.rule_serializer import validate_bundle
from backend.steps import StepRegistry

# Ensure steps are registered for validation
StepRegistry.discover()


class TestValidateBundle:
    def test_valid_bundle_returns_ok(self):
        bundle = RuleBundle(
            exported_at=datetime.now(UTC),
            source=SourceInfo(app_version="0.42.0"),
            rule=RuleDefinition(
                name="Test Rule",
                trigger_types=["sensor_event"],
            ),
            steps=[
                StepBundle(
                    label="scene_1",
                    step_type="scene_analysis",
                    config={"analysis_type": "objects"},
                ),
            ],
        )
        report = validate_bundle(bundle, "0.42.0")
        assert report.status == "ok"
        assert len(report.errors) == 0

    def test_unknown_step_type_is_error(self):
        bundle = RuleBundle(
            source=SourceInfo(app_version="0.42.0"),
            rule=RuleDefinition(
                name="Bad Rule",
                trigger_types=["sensor_event"],
            ),
            steps=[
                StepBundle(
                    label="bad_1",
                    step_type="nonexistent_step_type",
                    config={},
                ),
            ],
        )
        report = validate_bundle(bundle, "0.42.0")
        assert report.status == "error"
        assert any("nonexistent_step_type" in e for e in report.errors)

    def test_newer_app_version_is_warning(self):
        bundle = RuleBundle(
            source=SourceInfo(app_version="0.99.0"),
            rule=RuleDefinition(
                name="Future Rule",
                trigger_types=["sensor_event"],
            ),
            steps=[],
        )
        report = validate_bundle(bundle, "0.42.0")
        assert any("0.99.0" in w for w in report.warnings)

    def test_invalid_cron_expression_is_error(self):
        bundle = RuleBundle(
            source=SourceInfo(app_version="0.42.0"),
            rule=RuleDefinition(
                name="Cron Rule",
                trigger_types=["cron"],
                cron_expressions=[
                    CronExpressionRef(expression="not a cron expression", timezone="UTC"),
                ],
            ),
            steps=[],
        )
        report = validate_bundle(bundle, "0.42.0")
        assert report.status == "error"

    def test_step_schema_version_match_is_ok(self):
        bundle = RuleBundle(
            source=SourceInfo(app_version="0.42.0"),
            rule=RuleDefinition(
                name="Current Rule",
                trigger_types=["sensor_event"],
            ),
            steps=[
                StepBundle(
                    label="scene_1",
                    step_type="scene_analysis",
                    schema_version=1,
                    config={},
                ),
            ],
        )
        report = validate_bundle(bundle, "0.42.0")
        assert any(s.status == "ok" for s in report.steps)
