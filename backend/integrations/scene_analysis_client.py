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

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


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

    def __init__(self) -> None:
        self.base_url: str = (settings.get("scene_analysis.url") or "http://localhost:8100").rstrip(
            "/"
        )
        self.timeout: int = settings.get("scene_analysis.timeout", 30)
        self.enabled: bool = settings.get("scene_analysis.enabled", False)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict | None:
        """Return the service health dict, or None when unreachable."""
        if not self.enabled:
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
    # /detect — object detection only
    # ------------------------------------------------------------------

    async def detect(self, image_bytes: bytes) -> SceneDetectResult:
        """Run object detection on raw image bytes.

        Args:
            image_bytes: Raw image data (JPEG, PNG, etc.).

        Returns:
            :class:`SceneDetectResult` with detected objects, or an empty
            result when the service is unavailable.
        """
        if not self.enabled:
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

        return SceneDetectResult(
            detections=_parse_detections(data.get("detections", [])),
            detector_available=data.get("detector_available", False),
        )

    # ------------------------------------------------------------------
    # /describe — structured scene description only
    # ------------------------------------------------------------------

    async def describe(self, image_bytes: bytes) -> SceneDescribeResult:
        """Generate a structured scene description for raw image bytes.

        Args:
            image_bytes: Raw image data.

        Returns:
            :class:`SceneDescribeResult` with the description string, or an
            empty result when the service is unavailable.
        """
        if not self.enabled:
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

        return SceneDescribeResult(
            description=data.get("description", ""),
            describer_available=data.get("describer_available", False),
        )

    # ------------------------------------------------------------------
    # /analyze — full pipeline
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
        if not self.enabled:
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

        return SceneAnalyzeResult(
            detections=_parse_detections(data.get("detections", [])),
            description=data.get("description", ""),
            embedding=data.get("embedding", []),
            hazards=_parse_hazards(data.get("hazards", [])),
            detector_available=data.get("detector_available", False),
            describer_available=data.get("describer_available", False),
            embedder_available=data.get("embedder_available", False),
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_detections(raw: list[dict]) -> list[SceneDetection]:
    return [
        SceneDetection(
            label=d["label"],
            confidence=d["confidence"],
            bbox=d["bbox"],
            class_id=d["class_id"],
        )
        for d in raw
    ]


def _parse_hazards(raw: list[dict]) -> list[SceneHazardAlert]:
    return [
        SceneHazardAlert(
            name=h["name"],
            severity=h["severity"],
            description=h["description"],
            detection=SceneDetection(
                label=h["detection"]["label"],
                confidence=h["detection"]["confidence"],
                bbox=h["detection"]["bbox"],
                class_id=h["detection"]["class_id"],
            ),
        )
        for h in raw
    ]
