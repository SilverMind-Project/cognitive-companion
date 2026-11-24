"""Recording collaborators for knowledge delivery tests (the database is always real)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
from backend.tests.factories.companion_socket import CompanionSocketRouting

BASE_PERSONA = "You are Nila, the household companion."
VOICE = VoiceInstructionConfig(
    info_card_default="Read the card warmly.",
    quiz_default="Ask one question at a time.",
    quiz_gentle_directive="GENTLE: never say wrong.",
    quiz_standard_directive="STANDARD: say whether it was right.",
)


@dataclass
class RecordingWs(CompanionSocketRouting):
    broadcasts: list[dict[str, Any]] = field(default_factory=list)
    backend_tasks: list[dict[str, Any]] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)
    # Broadcast types and "backend_task" in the order they happened.
    order: list[str] = field(default_factory=list)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        self.broadcasts.append(payload)
        self.order.append(str(payload.get("type")))

    async def send_backend_task(self, prompt: str, callback: Any = None, **kwargs: Any) -> None:
        self.backend_tasks.append({"prompt": prompt, **kwargs})
        self.order.append("backend_task")

    async def release_voice_instruction(self, owner: str) -> bool:
        self.releases.append(owner)
        return True

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [b for b in self.broadcasts if b.get("type") == kind]


class RecordingScheduler:
    """A SchedulerBridge stand-in: a real (unstarted) APScheduler plus recorded resumes."""

    def __init__(self) -> None:
        self.apscheduler = AsyncIOScheduler()
        self.resumes: list[int] = []

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None:
        self.resumes.append(execution_id)


@dataclass
class FakeGrader:
    verdict: bool = True
    calls: int = 0

    async def grade_open_ended(self, question: str, expected: str, answer: str) -> bool:
        self.calls += 1
        # Yield like a real model call, so concurrent answers interleave here.
        await asyncio.sleep(0)
        return self.verdict


def make_delivery(
    db_factory: Any,
    *,
    grader: FakeGrader | None = None,
) -> tuple[KnowledgeDeliveryService, RecordingWs, RecordingScheduler]:
    ws = RecordingWs()
    scheduler = RecordingScheduler()
    service = KnowledgeDeliveryService(
        db_factory=db_factory,
        ws_manager=ws,  # type: ignore[arg-type]
        voice_instructions=VOICE,
        content_generation=grader,
        base_instruction=BASE_PERSONA,
        scheduler=scheduler,
    )
    return service, ws, scheduler
