"""Re-export all ORM models so that `import backend.models` registers them with Base."""

from backend.models.companion_surface import CompanionSurface
from backend.models.conversation import ConversationSession, ConversationTurn
from backend.models.cron_trigger import CronTrigger, RuleCronTrigger
from backend.models.cts_camera import CtsCamera
from backend.models.cts_dashboard import CtsAlertSuppression, CtsCameraOverlapGroup
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.cts_signal import DementiaSignal
from backend.models.cts_window_trigger import CtsWindowTrigger, RuleCtsWindowTrigger
from backend.models.event import EventLog
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.household_settings import HouseholdSettings
from backend.models.image_state import ActiveImageState
from backend.models.image_template import ImageTemplate
from backend.models.interactive_response import InteractiveResponse
from backend.models.knowledge import (
    InfoCard,
    InfoCardDelivery,
    InfoCardImageSlot,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    KnowledgeDocumentImage,
    Quiz,
    QuizQuestion,
    QuizResponse,
    QuizSession,
    SeniorKnowledgeQuery,
)
from backend.models.location_observation import LocationObservation
from backend.models.media_cache import MediaCache
from backend.models.occupancy import RoomOccupancyState
from backend.models.person import (
    ActivitySession,
    ActivityTypeEnum,
    DailyReport,
    HouseholdMember,
    PersonActivity,
    PersonLocationHistory,
    PersonLocationState,
    PersonSighting,
)
from backend.models.pipeline import PipelineEdge, PipelineStep, WorkflowExecution
from backend.models.presence_segment import PresenceSegment
from backend.models.room import Room
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor
from backend.models.transit_zone import TransitZone

__all__ = [
    "ActiveImageState",
    "ActivitySession",
    "ActivityTypeEnum",
    "CompanionSurface",
    "ConversationSession",
    "ConversationTurn",
    "CronTrigger",
    "CtsAlertSuppression",
    "CtsCamera",
    "CtsCameraOverlapGroup",
    "CtsIdentityRevisionLog",
    "CtsWindowTrigger",
    "DailyReport",
    "DementiaSignal",
    "EventLog",
    "GuidedSession",
    "GuidedSessionEvent",
    "HouseholdMember",
    "HouseholdSettings",
    "ImageTemplate",
    "InfoCard",
    "InfoCardDelivery",
    "InfoCardImageSlot",
    "InteractiveResponse",
    "KnowledgeDocument",
    "KnowledgeDocumentChunk",
    "KnowledgeDocumentImage",
    "LocationObservation",
    "MediaCache",
    "PersonActivity",
    "PersonLocationHistory",
    "PersonLocationState",
    "PersonSighting",
    "PipelineEdge",
    "PipelineStep",
    "PresenceSegment",
    "Quiz",
    "QuizQuestion",
    "QuizResponse",
    "QuizSession",
    "Room",
    "RoomOccupancyState",
    "Routine",
    "RoutineStep",
    "Rule",
    "RuleContext",
    "RuleCronTrigger",
    "RuleCtsWindowTrigger",
    "RuleDependency",
    "SeniorKnowledgeQuery",
    "Sensor",
    "TransitZone",
    "WorkflowExecution",
]
