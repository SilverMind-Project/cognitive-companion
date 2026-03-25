"""
VLLM-backed LLM providers using the OpenAI-compatible API.

* ``VLLMVisionProvider``      -- vision/multimodal (Cosmos-Reason2-8B)
* ``VLLMTranslationProvider`` -- text translation  (TranslateGemma)
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from backend.core.logging import get_logger
from backend.integrations.llm.base import LLMProvider

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 120.0  # seconds


def _encode_image_data_uri(path: str) -> str:
    """Read an image file and return a ``data:<mime>;base64,...`` URI."""
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/jpeg"
    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# VLLMVisionProvider
# ---------------------------------------------------------------------------


class VLLMVisionProvider(LLMProvider):
    """
    Calls a VLLM instance running a vision-capable model (e.g.
    ``nvidia/Cosmos-Reason2-8B``) through its OpenAI-compatible
    ``/v1/chat/completions`` endpoint.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "nvidia/Cosmos-Reason2-8B",
        max_tokens: int = 4096,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout

    # -- LLMProvider interface ------------------------------------------------

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
    ) -> str:
        content: list[dict[str, Any]] = []

        # Attach media --------------------------------------------------
        if media_paths:
            image_paths: list[str] = []

            if media_type == "video":
                # Delegate frame extraction to the media processor so that
                # VLLM receives still images rather than raw video.
                from backend.services.media_processor import extract_frames

                for video_path in media_paths:
                    frames_b64 = await extract_frames(video_path)
                    for b64 in frames_b64:
                        content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                },
                            }
                        )
            else:
                image_paths = media_paths

            for img in image_paths:
                data_uri = _encode_image_data_uri(img)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    }
                )

        # Always include the text prompt last so the model sees context
        # before the question.
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        logger.info(
            "vllm_vision_request",
            model=self.model,
            num_images=sum(1 for c in content if c["type"] == "image_url"),
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        text: str = data["choices"][0]["message"]["content"]
        logger.debug("vllm_vision_response", length=len(text))
        return text


# ---------------------------------------------------------------------------
# VLLMTranslationProvider
# ---------------------------------------------------------------------------


class VLLMTranslationProvider(LLMProvider):
    """
    Calls a VLLM instance running a translation model (e.g.
    ``TranslateGemma``) through its OpenAI-compatible endpoint.

    The prompt is formatted as::

        <<<source>>>en<<<target>>>ta<<<text>>>Hello world

    If the model returns a known hallucination artefact (the string
    ``"chennai"`` -- literally in Tamil script), the call is automatically
    retried up to ``max_retries`` times.
    """

    # Known bad output that signals a hallucinated / garbage response.
    _HALLUCINATION_MARKER = "\u0b9a\u0bc6\u0ba9\u0bcd\u0ba9\u0bc8"  # "சென்னை"

    def __init__(
        self,
        base_url: str,
        model: str = "TranslateGemma",
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout

    # -- LLMProvider interface ------------------------------------------------

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
        *,
        source_lang: str = "en",
        target_lang: str = "ta",
    ) -> str:
        """
        Translate *prompt* from *source_lang* to *target_lang*.

        ``media_paths`` and ``media_type`` are accepted for interface
        compatibility but ignored (translation is text-only).
        """
        formatted = (
            f"<<<source>>>{source_lang}"
            f"<<<target>>>{target_lang}"
            f"<<<text>>>{prompt}"
        )

        messages = [{"role": "user", "content": formatted}]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        last_text = ""
        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "vllm_translation_request",
                model=self.model,
                source=source_lang,
                target=target_lang,
                attempt=attempt,
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()

            data = response.json()
            last_text = data["choices"][0]["message"]["content"]

            if self._HALLUCINATION_MARKER not in last_text:
                logger.debug(
                    "vllm_translation_ok",
                    length=len(last_text),
                    attempt=attempt,
                )
                return last_text

            logger.warning(
                "vllm_translation_hallucination",
                attempt=attempt,
                marker=self._HALLUCINATION_MARKER,
            )

        # Exhausted retries -- return whatever we got last.
        logger.error(
            "vllm_translation_retries_exhausted",
            max_retries=self.max_retries,
        )
        return last_text
