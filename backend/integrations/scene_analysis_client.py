"""HTTP client for the scene-analysis-service.

Mirrors the pattern of :mod:`backend.integrations.person_id_client`:
configured from ``settings.yaml``, returns ``None`` / empty structures on
any failure so callers never need to handle exceptions.

Settings keys (under ``scene_analysis``)::

    scene_analysis:
      url: "http://localhost:8100"
      enabled: true
      timeout: 30

All three result dataclasses map 1-to-1 to the service's Pydantic response
models so the cognitive-companion backend never needs to import from the
scene-analysis-service package directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)
_PayloadModel = TypeVar("_PayloadModel", bound=BaseModel)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SceneDetection:
    """A single object-detection result from the scene-analysis-service."""

    label: str
    confidence: float
    bbox: list[float]
    class_id: int


@dataclass
class SceneHazardAlert:
    """A hazard flagged by the scene-analysis-service rule engine."""

    name: str
    severity: str
    description: str
    detection: SceneDetection


@dataclass
class SceneDetectResult:
    detections: list[SceneDetection] = field(default_factory=list)
    detector_available: bool = False


@dataclass
class SceneDescribeResult:
    description: str = ""
    describer_available: bool = False


@dataclass
class SceneAnalyzeResult:
    detections: list[SceneDetection] = field(default_factory=list)
    description: str = ""
    embedding: list[float] = field(default_factory=list)
    hazards: list[SceneHazardAlert] = field(default_factory=list)
    detector_available: bool = False
    describer_available: bool = False
    embedder_available: bool = False


class _SceneDetectionPayload(BaseModel):
    label: str
    confidence: float
    bbox: list[float]
    class_id: int

    def to_result(self) -> SceneDetection:
        return SceneDetection(
            label=self.label,
            confidence=self.confidence,
            bbox=self.bbox,
            class_id=self.class_id,
        )


class _SceneHazardPayload(BaseModel):
    name: str
    severity: str
    description: str
    detection: _SceneDetectionPayload

    def to_result(self) -> SceneHazardAlert:
        return SceneHazardAlert(
            name=self.name,
            severity=self.severity,
            description=self.description,
            detection=self.detection.to_result(),
        )


class _SceneDetectPayload(BaseModel):
    detections: list[_SceneDetectionPayload] = Field(default_factory=list)
    detector_available: bool = False

    @field_validator("detections", mode="before")
    @classmethod
    def _filter_detections(cls, value: object) -> list[_SceneDetectionPayload]:
        return _validate_payload_list(value, _SceneDetectionPayload)

    def to_result(self) -> SceneDetectResult:
        return SceneDetectResult(
            detections=[item.to_result() for item in self.detections],
            detector_available=self.detector_available,
        )


class _SceneDescribePayload(BaseModel):
    description: str = ""
    describer_available: bool = False

    def to_result(self) -> SceneDescribeResult:
        return SceneDescribeResult(
            description=self.description,
            describer_available=self.describer_available,
        )


class _SceneAnalyzePayload(BaseModel):
    detections: list[_SceneDetectionPayload] = Field(default_factory=list)
    description: str = ""
    embedding: list[float] = Field(default_factory=list)
    hazards: list[_SceneHazardPayload] = Field(default_factory=list)
    detector_available: bool = False
    describer_available: bool = False
    embedder_available: bool = False

    @field_validator("detections", mode="before")
    @classmethod
    def _filter_detections(cls, value: object) -> list[_SceneDetectionPayload]:
        return _validate_payload_list(value, _SceneDetectionPayload)

    @field_validator("hazards", mode="before")
    @classmethod
    def _filter_hazards(cls, value: object) -> list[_SceneHazardPayload]:
        return _validate_payload_list(value, _SceneHazardPayload)

    @field_validator("embedding", mode="before")
    @classmethod
    def _filter_embedding(cls, value: object) -> list[float]:
        if not isinstance(value, list):
            return []
        parsed: list[float] = []
        for item in value:
            try:
                parsed.append(float(item))
            except (TypeError, ValueError):
                continue
        return parsed

    def to_result(self) -> SceneAnalyzeResult:
        return SceneAnalyzeResult(
            detections=[item.to_result() for item in self.detections],
            description=self.description,
            embedding=self.embedding,
            hazards=[item.to_result() for item in self.hazards],
            detector_available=self.detector_available,
            describer_available=self.describer_available,
            embedder_available=self.embedder_available,
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SceneAnalysisClient:
    """Async HTTP client for the scene-analysis-service.

    All public methods return ``None`` / empty result objects when:
    * The client is disabled (``scene_analysis.enabled: false``).
    * The service is unreachable or returns a non-2xx response.
    * The image data is malformed.

    This ensures downstream pipeline steps can always call these methods
    without defensive null-checking on the result.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.base_url: str = (
            base_url if base_url is not None else settings.get_required("scene_analysis.url")
        ).rstrip("/")
        self.timeout: float = float(
            timeout if timeout is not None else settings.get_required("scene_analysis.timeout")
        )
        self.enabled: bool = (
            bool(enabled)
            if enabled is not None
            else bool(settings.get_required("scene_analysis.enabled"))
        )

    @property
    def configured(self) -> bool:
        """Whether the client is enabled and has a target URL."""
        return self.enabled and bool(self.base_url)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict | None:
        """Return the service health dict, or None when unreachable."""
        if not self.configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.warning("scene_analysis_health_check_failed")
            return None

    # ------------------------------------------------------------------
    # /detect: object detection only
    # ------------------------------------------------------------------

    async def detect(self, image_bytes: bytes) -> SceneDetectResult:
        """Run object detection on raw image bytes.

        Args:
            image_bytes: Raw image data (JPEG, PNG, etc.).

        Returns:
            :class:`SceneDetectResult` with detected objects, or an empty
            result when the service is unavailable.
        """
        if not self.configured:
            return SceneDetectResult()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/detect",
                    files={"image": ("image.jpg", image_bytes, "image/jpeg")},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("scene_analysis_detect_failed")
            return SceneDetectResult()
        payload = _validate_response_payload(
            data,
            _SceneDetectPayload,
            log_event="scene_analysis_detect_invalid_payload",
        )
        return payload.to_result() if payload is not None else SceneDetectResult()

    # ------------------------------------------------------------------
    # /describe: structured scene description only
    # ------------------------------------------------------------------

    async def describe(self, image_bytes: bytes) -> SceneDescribeResult:
        """Generate a structured scene description for raw image bytes.

        Args:
            image_bytes: Raw image data.

        Returns:
            :class:`SceneDescribeResult` with the description string, or an
            empty result when the service is unavailable.
        """
        if not self.configured:
            return SceneDescribeResult()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/describe",
                    files={"image": ("image.jpg", image_bytes, "image/jpeg")},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("scene_analysis_describe_failed")
            return SceneDescribeResult()
        payload = _validate_response_payload(
            data,
            _SceneDescribePayload,
            log_event="scene_analysis_describe_invalid_payload",
        )
        return payload.to_result() if payload is not None else SceneDescribeResult()

    # ------------------------------------------------------------------
    # /analyze: full pipeline
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
        """Run the full analysis pipeline on raw image bytes.

        Args:
            image_bytes: Raw image data.
            run_detect: Whether to run object detection.
            run_describe: Whether to run scene description.
            run_embed: Whether to run CLIP embedding.
            run_hazards: Whether to evaluate hazard rules.

        Returns:
            :class:`SceneAnalyzeResult` with populated fields for each
            enabled stage, or an empty result when the service is unavailable.
        """
        if not self.configured:
            return SceneAnalyzeResult()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/analyze",
                    params={
                        "run_detect": str(run_detect).lower(),
                        "run_describe": str(run_describe).lower(),
                        "run_embed": str(run_embed).lower(),
                        "run_hazards": str(run_hazards).lower(),
                    },
                    files={"image": ("image.jpg", image_bytes, "image/jpeg")},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("scene_analysis_analyze_failed")
            return SceneAnalyzeResult()
        payload = _validate_response_payload(
            data,
            _SceneAnalyzePayload,
            log_event="scene_analysis_analyze_invalid_payload",
        )
        return payload.to_result() if payload is not None else SceneAnalyzeResult()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_payload_list(
    raw_items: object,
    model_cls: type[_PayloadModel],
) -> list[_PayloadModel]:
    if not isinstance(raw_items, list):
        return []

    validated_items: list[_PayloadModel] = []
    for item in raw_items:
        try:
            validated_items.append(model_cls.model_validate(item))
        except ValidationError:
            continue
    return validated_items


def _validate_response_payload(
    data: object,
    model_cls: type[_PayloadModel],
    *,
    log_event: str,
) -> _PayloadModel | None:
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        logger.warning(log_event)
        return None
