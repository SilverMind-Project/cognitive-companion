"""Integration test to verify InteractiveResponseService is properly registered in ServiceContainer."""

from unittest.mock import MagicMock

from backend.services.interactive_response import InteractiveResponseService
from backend.services.pipeline_executor import PipelineExecutor
from backend.steps.base import ServiceContainer


def test_interactive_response_service_in_service_container():
    """Verify that InteractiveResponseService can be added to ServiceContainer."""
    # Create a mock service
    mock_service = MagicMock(spec=InteractiveResponseService)

    # Create ServiceContainer with the service
    container = ServiceContainer(
        db_factory=MagicMock(),
        interactive_response_service=mock_service,
    )

    # Verify the service is accessible
    assert container.interactive_response_service is not None
    assert container.interactive_response_service == mock_service


def test_pipeline_executor_accepts_interactive_response_service():
    """Verify that PipelineExecutor accepts and stores InteractiveResponseService."""
    # Create a mock service
    mock_service = MagicMock(spec=InteractiveResponseService)
    mock_db_factory = MagicMock()

    # Create PipelineExecutor with the service
    executor = PipelineExecutor(
        db_session_factory=mock_db_factory,
        interactive_response_service=mock_service,
    )

    # Verify the service is stored in the internal ServiceContainer
    assert executor._services.interactive_response_service is not None
    assert executor._services.interactive_response_service == mock_service


def test_service_container_has_all_required_fields():
    """Verify that ServiceContainer has all expected service fields."""
    container = ServiceContainer(db_factory=MagicMock())

    # Check that all expected fields exist
    expected_fields = [
        "db_factory",
        "person_tracking",
        "person_id_client",
        "notification_dispatcher",
        "ha_client",
        "event_aggregator",
        "scheduler",
        "rag_service",
        "llm_model_registry",
        "scene_analysis_client",
        "daily_report_service",
        "semantic_memory_client",
        "interactive_response_service",
    ]

    for field in expected_fields:
        assert hasattr(container, field), f"ServiceContainer missing field: {field}"
