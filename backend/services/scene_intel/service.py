"""SceneIntelService -- write-side wrapper around scene-analysis + semantic-memory.

Consolidates the pattern in ``scene_analysis.py`` (analyze -> optionally
write observation) into one method, plus adds movement persistence.
Removes the pipeline-step author's need to know about ``ObservationCreate``
and ``MovementCreate`` schemas.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.integrations.scene_analysis_client import (
    SceneAnalysisClient,
    SceneAnalyzeResult,
)
from backend.integrations.semantic_memory_client import (
    MovementCreate,
    ObservationCreate,
    SemanticMemoryClient,
)
from backend.services.scene_intel.types import (
    RoomTransition,
    SceneIntelRecord,
)

logger = get_logger(__name__)


class SceneIntelService:
    """Write-side wrapper around scene-analysis and semantic-memory clients.

    Constructor:

    - ``scene_client``: ``SceneAnalysisClient | None``.  When ``None``,
      ``analyze()`` returns an empty ``SceneAnalyzeResult``.
    - ``memory_client``: ``SemanticMemoryClient | None``.  When ``None``,
      ``persist()`` returns ``SceneIntelRecord.empty()`` without calling
      any HTTP endpoint.
    """

    def __init__(
        self,
        *,
        scene_client: SceneAnalysisClient | None,
        memory_client: SemanticMemoryClient | None,
    ) -> None:
        self._scene_client = scene_client
        self._memory_client = memory_client

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        run_detect: bool = True,
        run_describe: bool = True,
        run_embed: bool = True,
        run_hazards: bool = True,
    ) -> SceneAnalyzeResult:
        """Run scene analysis on image bytes.

        Pass-through to ``scene_client.analyze()``.  When
        ``scene_client`` is ``None``, returns an empty result.
        """
        if self._scene_client is None:
            return SceneAnalyzeResult()

        return await self._scene_client.analyze(
            image_bytes,
            run_detect=run_detect,
            run_describe=run_describe,
            run_embed=run_embed,
            run_hazards=run_hazards,
        )

    # ------------------------------------------------------------------
    # persist
    # ------------------------------------------------------------------

    async def persist(
        self,
        result: SceneAnalyzeResult,
        *,
        room_id: str,
        source: str = "scene_intel",
        transitions: tuple[RoomTransition, ...] = (),
    ) -> SceneIntelRecord:
        """Persist a scene analysis result to semantic memory.

        Builds an ``ObservationCreate`` from the analysis result and
        calls ``memory_client.create_observation()``.  For each
        ``RoomTransition``, builds a ``MovementCreate`` and calls
        ``memory_client.create_movement()``.

        Returns a ``SceneIntelRecord`` with the observation ID and
        movement IDs.
        """
        if self._memory_client is None:
            return SceneIntelRecord.empty()

        # Build observation payload.
        description = result.description or ""
        object_list = [d.label for d in result.detections]
        hazard_flags = [h.name for h in result.hazards]
        embedding = result.embedding if isinstance(result.embedding, list) else []

        # Skip persistence if all four are empty.
        if not description and not object_list and not hazard_flags and not embedding:
            logger.info(
                "scene_persist_skipped_empty",
                room_id=room_id,
            )
            return SceneIntelRecord.empty()

        obs = ObservationCreate(
            room_id=room_id,
            description=description,
            object_list=object_list,
            hazard_flags=hazard_flags,
            embedding=embedding,
            source=source,
        )

        record = await self._memory_client.create_observation(obs)
        observation_id: int | None = record.id if record else None

        # Write movements, linked to the observation.
        movement_ids: list[int] = []
        for transition in transitions:
            try:
                movement = MovementCreate(
                    person_id=transition.person_id,
                    from_room_id=transition.from_room_id,
                    to_room_id=transition.to_room_id,
                    direction_semantic=transition.direction_semantic,
                    confidence=transition.confidence,
                    observation_id=observation_id,
                )
                move_record = await self._memory_client.create_movement(movement)
                if move_record:
                    movement_ids.append(move_record.id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "movement_persist_failed",
                    person_id=transition.person_id,
                    from_room=transition.from_room_id,
                    to_room=transition.to_room_id,
                )

        return SceneIntelRecord(
            observation_id=observation_id,
            movement_ids=movement_ids,
            source=source,
        )

    # ------------------------------------------------------------------
    # analyze_and_persist
    # ------------------------------------------------------------------

    async def analyze_and_persist(
        self,
        image_bytes: bytes,
        *,
        room_id: str,
        source: str = "scene_intel",
        run_detect: bool = True,
        run_describe: bool = True,
        run_embed: bool = True,
        run_hazards: bool = True,
        transitions: tuple[RoomTransition, ...] = (),
    ) -> SceneIntelRecord:
        """Analyze an image and persist the result in one call.

        Composition of ``analyze()`` + ``persist()``.
        """
        result = await self.analyze(
            image_bytes,
            run_detect=run_detect,
            run_describe=run_describe,
            run_embed=run_embed,
            run_hazards=run_hazards,
        )
        return await self.persist(
            result,
            room_id=room_id,
            source=source,
            transitions=transitions,
        )
