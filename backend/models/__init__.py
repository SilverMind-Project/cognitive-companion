"""Re-export all ORM models so that `import backend.models` registers them with Base."""

from backend.models.alert import EmergencyAlert
from backend.models.conversation import ConversationSession, ConversationTurn
from backend.models.event import EventLog
from backend.models.image_state import ActiveImageState
from backend.models.image_template import ImageTemplate
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
    "DailyReport",
    "EmergencyAlert",
    "EventLog",
    "HouseholdMember",
    "ImageTemplate",
    "MediaCache",
    "PersonActivity",
    "PersonLocationHistory",
    "PersonLocationState",
    "PersonSighting",
    "PipelineStep",
    "Room",
    "Rule",
    "RuleContext",
    "RuleDependency",
    "Sensor",
    "WorkflowExecution",
]
