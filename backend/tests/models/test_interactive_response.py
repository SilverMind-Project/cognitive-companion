"""Unit tests for InteractiveResponse model.

**Validates: Requirements 23.1, 27.8**

Tests model instantiation, field validation, unique constraint enforcement,
JSON field serialization/deserialization, and timezone-aware datetime handling.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.interactive_response import InteractiveResponse
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workflow_execution(db_session):
    """Create a minimal WorkflowExecution for FK constraints."""
    rule = Rule(
        name="Test Rule",
        description="Test rule for interactive response tests",
        enabled=True,
    )
    db_session.add(rule)
    db_session.flush()

    execution = WorkflowExecution(
        rule_id=rule.id,
        status="running",
        pipeline_data_json={},
    )
    db_session.add(execution)
    db_session.flush()
    return execution


@pytest.fixture
def pipeline_step(db_session, workflow_execution):
    """Create a minimal PipelineStep for FK constraints."""
    step = PipelineStep(
        rule_id=workflow_execution.rule_id,
        step_type="interactive_prompt",
        config_json={},
        order=1,
    )
    db_session.add(step)
    db_session.flush()
    return step


# ---------------------------------------------------------------------------
# Model Instantiation and Field Validation
# ---------------------------------------------------------------------------


class TestModelInstantiation:
    def test_create_with_all_fields(self, db_session, workflow_execution, pipeline_step):
        """Test creating InteractiveResponse with all required fields."""
        timestamp = datetime(2024, 1, 15, 10, 30, 15, tzinfo=UTC)
        raw_response = {"button_id": "escalate", "user_agent": "Mozilla/5.0"}

        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
            raw_response_json=raw_response,
        )
        db_session.add(response)
        db_session.flush()

        assert response.id is not None
        assert response.execution_id == workflow_execution.id
        assert response.step_id == pipeline_step.id
        assert response.channel == "pwa_popup_text"
        assert response.action == "escalate"
        assert response.timestamp == timestamp
        assert response.raw_response_json == raw_response
        assert response.created_at is not None

    def test_create_with_minimal_fields(self, db_session, workflow_execution, pipeline_step):
        """Test creating InteractiveResponse with minimal required fields."""
        timestamp = datetime.now(UTC)

        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="timeout",
            action="dismiss",
            timestamp=timestamp,
        )
        db_session.add(response)
        db_session.flush()

        assert response.id is not None
        assert response.raw_response_json == {}  # Default value

    def test_created_at_auto_populated(self, db_session, workflow_execution, pipeline_step):
        """Test that created_at is automatically populated on insert."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_realtime_ai",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)
        db_session.flush()

        assert response.created_at is not None
        # Verify created_at is recent (within last 5 seconds)
        now = datetime.now(UTC)
        time_diff = (now - response.created_at).total_seconds()
        assert 0 <= time_diff < 5


# ---------------------------------------------------------------------------
# Unique Constraint Enforcement
# ---------------------------------------------------------------------------


class TestUniqueConstraint:
    def test_unique_constraint_on_execution_step(
        self, db_session, workflow_execution, pipeline_step
    ):
        """Test that (execution_id, step_id) unique constraint is enforced."""
        timestamp1 = datetime(2024, 1, 15, 10, 30, 15, tzinfo=UTC)
        timestamp2 = datetime(2024, 1, 15, 10, 30, 20, tzinfo=UTC)

        # First response succeeds
        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp1,
        )
        db_session.add(response1)
        db_session.flush()

        # Second response with same execution_id and step_id should fail
        response2 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_realtime_ai",  # Different channel
            action="dismiss",  # Different action
            timestamp=timestamp2,  # Different timestamp
        )
        db_session.add(response2)

        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_different_execution_id_allows_duplicate_step_id(
        self, db_session, workflow_execution, pipeline_step
    ):
        """Test that different execution_id allows same step_id."""
        # Create second execution
        execution2 = WorkflowExecution(
            rule_id=workflow_execution.rule_id,
            status="running",
            pipeline_data_json={},
        )
        db_session.add(execution2)
        db_session.flush()

        timestamp = datetime.now(UTC)

        # First response
        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
        )
        db_session.add(response1)
        db_session.flush()

        # Second response with different execution_id should succeed
        response2 = InteractiveResponse(
            execution_id=execution2.id,
            step_id=pipeline_step.id,  # Same step_id
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
        )
        db_session.add(response2)
        db_session.flush()

        assert response1.id != response2.id

    def test_different_step_id_allows_duplicate_execution_id(
        self, db_session, workflow_execution, pipeline_step
    ):
        """Test that different step_id allows same execution_id."""
        # Create second step
        step2 = PipelineStep(
            rule_id=workflow_execution.rule_id,
            step_type="interactive_prompt",
            config_json={},
            order=2,
        )
        db_session.add(step2)
        db_session.flush()

        timestamp = datetime.now(UTC)

        # First response
        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
        )
        db_session.add(response1)
        db_session.flush()

        # Second response with different step_id should succeed
        response2 = InteractiveResponse(
            execution_id=workflow_execution.id,  # Same execution_id
            step_id=step2.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
        )
        db_session.add(response2)
        db_session.flush()

        assert response1.id != response2.id


# ---------------------------------------------------------------------------
# JSON Field Serialization/Deserialization
# ---------------------------------------------------------------------------


class TestJSONField:
    def test_json_field_stores_dict(self, db_session, workflow_execution, pipeline_step):
        """Test that raw_response_json stores and retrieves dict correctly."""
        raw_response = {
            "button_id": "escalate",
            "user_agent": "Mozilla/5.0",
            "ip_address": "192.168.1.1",
        }

        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response_json=raw_response,
        )
        db_session.add(response)
        db_session.flush()

        # Retrieve from database
        retrieved = db_session.get(InteractiveResponse, response.id)
        assert retrieved.raw_response_json == raw_response

    def test_json_field_stores_nested_structures(
        self, db_session, workflow_execution, pipeline_step
    ):
        """Test that raw_response_json handles nested structures."""
        raw_response = {
            "needs_help": True,
            "user_statement": "I fell down",
            "metadata": {
                "confidence": 0.95,
                "language": "en-US",
                "keywords": ["fell", "down"],
            },
        }

        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_realtime_ai",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response_json=raw_response,
        )
        db_session.add(response)
        db_session.flush()

        # Retrieve from database
        retrieved = db_session.get(InteractiveResponse, response.id)
        assert retrieved.raw_response_json == raw_response
        assert retrieved.raw_response_json["metadata"]["keywords"] == ["fell", "down"]

    def test_json_field_default_empty_dict(self, db_session, workflow_execution, pipeline_step):
        """Test that raw_response_json defaults to empty dict."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="timeout",
            action="dismiss",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)
        db_session.flush()

        assert response.raw_response_json == {}

    def test_json_field_stores_empty_dict(self, db_session, workflow_execution, pipeline_step):
        """Test that raw_response_json can explicitly store empty dict."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="timeout",
            action="dismiss",
            timestamp=datetime.now(UTC),
            raw_response_json={},
        )
        db_session.add(response)
        db_session.flush()

        retrieved = db_session.get(InteractiveResponse, response.id)
        assert retrieved.raw_response_json == {}


# ---------------------------------------------------------------------------
# Timezone-Aware Datetime Handling
# ---------------------------------------------------------------------------


class TestTimezoneAwareDatetime:
    def test_timestamp_preserves_utc_timezone(self, db_session, workflow_execution, pipeline_step):
        """Test that timestamp field preserves UTC timezone information."""
        timestamp = datetime(2024, 1, 15, 10, 30, 15, tzinfo=UTC)

        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp,
        )
        db_session.add(response)
        db_session.flush()

        # Clear session to force reload from database
        db_session.expire(response)
        retrieved = db_session.get(InteractiveResponse, response.id)

        assert retrieved.timestamp.tzinfo is not None
        assert retrieved.timestamp == timestamp

    def test_created_at_is_timezone_aware(self, db_session, workflow_execution, pipeline_step):
        """Test that created_at field is timezone-aware."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)
        db_session.flush()

        # Clear session to force reload from database
        db_session.expire(response)
        retrieved = db_session.get(InteractiveResponse, response.id)

        assert retrieved.created_at.tzinfo is not None

    def test_timestamp_comparison_across_timezones(
        self, db_session, workflow_execution, pipeline_step
    ):
        """Test that timestamps can be compared correctly."""
        timestamp1 = datetime(2024, 1, 15, 10, 30, 15, tzinfo=UTC)
        timestamp2 = datetime(2024, 1, 15, 10, 30, 20, tzinfo=UTC)

        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp1,
        )
        db_session.add(response1)
        db_session.flush()

        # Create second execution and step for unique constraint
        execution2 = WorkflowExecution(
            rule_id=workflow_execution.rule_id,
            status="running",
            pipeline_data_json={},
        )
        db_session.add(execution2)
        db_session.flush()

        response2 = InteractiveResponse(
            execution_id=execution2.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=timestamp2,
        )
        db_session.add(response2)
        db_session.flush()

        assert response1.timestamp < response2.timestamp


# ---------------------------------------------------------------------------
# Foreign Key Relationships
# ---------------------------------------------------------------------------


class TestForeignKeyRelationships:
    def test_execution_id_foreign_key_constraint(self, db_session, pipeline_step):
        """Test that execution_id must reference valid WorkflowExecution."""
        response = InteractiveResponse(
            execution_id=99999,  # Non-existent execution_id
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)

        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_step_id_foreign_key_constraint(self, db_session, workflow_execution):
        """Test that step_id must reference valid PipelineStep."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=99999,  # Non-existent step_id
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)

        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# Query and Retrieval
# ---------------------------------------------------------------------------


class TestQueryAndRetrieval:
    def test_query_by_execution_id(self, db_session, workflow_execution, pipeline_step):
        """Test querying responses by execution_id."""
        # Create multiple responses for same execution
        step2 = PipelineStep(
            rule_id=workflow_execution.rule_id,
            step_type="interactive_prompt",
            config_json={},
            order=2,
        )
        db_session.add(step2)
        db_session.flush()

        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        response2 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=step2.id,
            channel="pwa_realtime_ai",
            action="dismiss",
            timestamp=datetime.now(UTC),
        )
        db_session.add_all([response1, response2])
        db_session.flush()

        # Query by execution_id
        responses = (
            db_session.query(InteractiveResponse)
            .filter(InteractiveResponse.execution_id == workflow_execution.id)
            .all()
        )

        assert len(responses) == 2
        assert {r.step_id for r in responses} == {pipeline_step.id, step2.id}

    def test_query_by_execution_and_step(self, db_session, workflow_execution, pipeline_step):
        """Test querying response by execution_id and step_id."""
        response = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        db_session.add(response)
        db_session.flush()

        # Query by execution_id and step_id
        retrieved = (
            db_session.query(InteractiveResponse)
            .filter(
                InteractiveResponse.execution_id == workflow_execution.id,
                InteractiveResponse.step_id == pipeline_step.id,
            )
            .first()
        )

        assert retrieved is not None
        assert retrieved.id == response.id

    def test_query_by_channel(self, db_session, workflow_execution, pipeline_step):
        """Test querying responses by channel."""
        # Create second execution and step for unique constraint
        execution2 = WorkflowExecution(
            rule_id=workflow_execution.rule_id,
            status="running",
            pipeline_data_json={},
        )
        db_session.add(execution2)
        db_session.flush()

        response1 = InteractiveResponse(
            execution_id=workflow_execution.id,
            step_id=pipeline_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
        )
        response2 = InteractiveResponse(
            execution_id=execution2.id,
            step_id=pipeline_step.id,
            channel="pwa_realtime_ai",
            action="dismiss",
            timestamp=datetime.now(UTC),
        )
        db_session.add_all([response1, response2])
        db_session.flush()

        # Query by channel
        popup_responses = (
            db_session.query(InteractiveResponse)
            .filter(InteractiveResponse.channel == "pwa_popup_text")
            .all()
        )

        assert len(popup_responses) == 1
        assert popup_responses[0].id == response1.id
