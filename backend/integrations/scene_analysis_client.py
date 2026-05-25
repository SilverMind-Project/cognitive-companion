"""HTTP client for the scene-analysis-service.

Rebuilt on top of :mod:`backend.integrations._http_base`.  Public surface
and dataclass names are identical to the previous implementation so all
existing callers compile without changes.

Settings keys (under ``scene_analysis``)::

    scene_analysis:
      url: "http://localhost:8100"
      enabled: true
      timeout: 30
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.core.logging import get_logger

from ._http_base import HttpUpstreamClient

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Frozen result dataclasses (public API surface)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneDetection:
    """A single object-detection result from the scene-analysis-service."""

    label: str
    confidence: float
    bbox: list[float]
    class_id: int


@dataclass(frozen=True)
class SceneHazardAlert:
    """A hazard flagged by the scene-analysis-service rule engine."""

    name: str
    severity: str
    description: str
    detection: SceneDetection


@dataclass(frozen=True)
class SceneDetectResult:
    detections: list[SceneDetection] = field(default_factory=list)
    detector_available: bool = False


@dataclass(frozen=True)
class SceneDescribeResult:
    description: str = ""
    describer_available: bool = False


@dataclass(frozen=True)
class SceneAnalyzeResult:
    detections: list[SceneDetection] = field(default_factory=list)
    description: str = ""
    embedding: list[float] = field(default_factory=list)
    hazards: list[SceneHazardAlert] = field(default_factory=list)
    detector_available: bool = False
    describer_available: bool = False
    embedder_available: bool = False


# ---------------------------------------------------------------------------
# Pydantic wire-level payloads (private)
# ---------------------------------------------------------------------------


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
            except TypeError, ValueError:
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


class SceneAnalysisClient(HttpUpstreamClient):
    """Async HTTP client for the scene-analysis-service.

    All public methods return ``None`` / empty result objects when:
    * The client is disabled (``scene_analysis.enabled: false``).
    * The service is unreachable or returns a non-2xx response.
    * The image data is malformed.

    This ensures downstream pipeline steps can always call these methods
    without defensive null-checking on the result.
    """

    SETTINGS_PREFIX = "scene_analysis"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict | None:
        """Return the service health dict, or None when unreachable."""
        return await self._get_json("/health")

    # ------------------------------------------------------------------
    # /detect: object detection only
    # ------------------------------------------------------------------

    def _sensor_headers(self, sensor_id: str | None) -> dict[str, str]:
        if sensor_id is not None:
            return {"X-Sensor-Id": sensor_id}
        return {}

    # ------------------------------------------------------------------
    # /detect: object detection only
    # ------------------------------------------------------------------

    async def detect(
        self,
        image_bytes: bytes,
        *,
        sensor_id: str | None = None,
    ) -> SceneDetectResult:
        """Run object detection on raw image bytes."""
        data = await self._post_multipart(
            "/detect",
            files={"image": ("image.jpg", image_bytes, "image/jpeg")},
            headers=self._sensor_headers(sensor_id),
        )
        if data is None:
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

    async def describe(
        self,
        image_bytes: bytes,
        *,
        sensor_id: str | None = None,
    ) -> SceneDescribeResult:
        """Generate a structured scene description for raw image bytes."""
        data = await self._post_multipart(
            "/describe",
            files={"image": ("image.jpg", image_bytes, "image/jpeg")},
            headers=self._sensor_headers(sensor_id),
        )
        if data is None:
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
        sensor_id: str | None = None,
    ) -> SceneAnalyzeResult:
        """Run the full analysis pipeline on raw image bytes."""
        data = await self._post_multipart(
            "/analyze",
            files={"image": ("image.jpg", image_bytes, "image/jpeg")},
            params={
                "run_detect": str(run_detect).lower(),
                "run_describe": str(run_describe).lower(),
                "run_embed": str(run_embed).lower(),
                "run_hazards": str(run_hazards).lower(),
            },
            headers=self._sensor_headers(sensor_id),
        )
        if data is None:
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


def _validate_payload_list[PayloadModelT: BaseModel](
    raw_items: object,
    model_cls: type[PayloadModelT],
) -> list[PayloadModelT]:
    if not isinstance(raw_items, list):
        return []

    validated_items: list[PayloadModelT] = []
    for item in raw_items:
        try:
            validated_items.append(model_cls.model_validate(item))
        except ValidationError:
            continue
    return validated_items


def _validate_response_payload[PayloadModelT: BaseModel](
    data: object,
    model_cls: type[PayloadModelT],
    *,
    log_event: str,
) -> PayloadModelT | None:
    try:
        return model_cls.model_validate(data)
    except ValidationError:
        logger.warning(log_event)
        return None
