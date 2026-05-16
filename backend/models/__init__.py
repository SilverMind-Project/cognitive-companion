"""Re-export all ORM models so that `import backend.models` registers them with Base."""

from backend.models.alert import EmergencyAlert
from backend.models.conversation import ConversationSession, ConversationTurn
from backend.models.cron_trigger import CronTrigger, RuleCronTrigger
from backend.models.cts_camera import CtsCamera
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.cts_signal import DementiaSignal
from backend.models.cts_window_trigger import CtsWindowTrigger, RuleCtsWindowTrigger
from backend.models.event import EventLog
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
from backend.models.media_cache import MediaCache
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
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.room import Room
from backend.models.rule import Rule, RuleContext, RuleDependency
from backend.models.sensor import Sensor

__all__ = [
    "ActiveImageState",
    "ActivitySession",
    "ActivityTypeEnum",
    "ConversationSession",
    "ConversationTurn",
    "CronTrigger",
    "CtsCamera",
    "CtsIdentityRevisionLog",
    "CtsWindowTrigger",
    "DailyReport",
    "DementiaSignal",
    "EmergencyAlert",
    "EventLog",
    "HouseholdMember",
    "ImageTemplate",
    "InfoCard",
    "InfoCardDelivery",
    "InfoCardImageSlot",
    "InteractiveResponse",
    "KnowledgeDocument",
    "KnowledgeDocumentChunk",
    "KnowledgeDocumentImage",
    "MediaCache",
    "PersonActivity",
    "PersonLocationHistory",
    "PersonLocationState",
    "PersonSighting",
    "PipelineStep",
    "Quiz",
    "QuizQuestion",
    "QuizResponse",
    "QuizSession",
    "Room",
    "Rule",
    "RuleContext",
    "RuleCronTrigger",
    "RuleCtsWindowTrigger",
    "RuleDependency",
    "SeniorKnowledgeQuery",
    "Sensor",
    "WorkflowExecution",
]
