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
from tenacity import AsyncRetrying, RetryError, retry_if_result, stop_after_attempt

from backend.core.logging import get_logger
from backend.integrations.llm.base import THINKING_INSTRUCTION, LLMProvider, strip_thinking

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 120.0  # seconds


async def _encode_image_data_uri(path: str) -> str:
    """Read an image file (or fetch a URL) and return a ``data:<mime>;base64,...`` URI."""
    if path.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(path)
            response.raise_for_status()
        raw = response.content
        content_type = response.headers.get("content-type", "")
        mime = content_type.split(";")[0].strip() or "image/jpeg"
    else:
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = "image/jpeg"
        raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    logger.info(f"mime type: {mime}, content length: {len(b64)}")
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
        max_tokens: int = 16000,
        timeout: float = _DEFAULT_TIMEOUT,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p

    # -- LLMProvider interface ------------------------------------------------

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
        response_schema: dict | None = None,
        thinking: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
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
                data_uri = await _encode_image_data_uri(img)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    }
                )

        # Text prompt last so the model sees images before the question.
        content.append({"type": "text", "text": prompt})

        # Chain-of-thought instruction appended after the prompt so the
        # model reads the question first, then sees the output format.
        if thinking:
            content.append({"type": "text", "text": THINKING_INSTRUCTION})

        messages = [{"role": "user", "content": content}]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }

        # Sampling overrides (call-time wins; instance default wins over nothing)
        effective_temperature = temperature if temperature is not None else self.temperature
        effective_top_p = top_p if top_p is not None else self.top_p
        if effective_temperature is not None:
            payload["temperature"] = effective_temperature
        if effective_top_p is not None:
            payload["top_p"] = effective_top_p

        # Schema-enforced structured output via vLLM guided decoding
        if response_schema:
            payload["guided_json"] = response_schema

        logger.info(
            "vllm_vision_request",
            model=self.model,
            num_images=sum(1 for c in content if c["type"] == "image_url"),
            max_tokens=payload["max_tokens"]
        )
        logger.info(f"payload keys: {payload.keys}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        logger.info(f"vllm vision response data: {data}")
        text: str = data["choices"][0]["message"]["content"] or ""
        if thinking:
            text = strip_thinking(text)
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
    _HALLUCINATION_MARKER = "சென்னை"  # "chennai" in Tamil script

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
        response_schema: dict | None = None,
        *,
        source_lang: str = "en",
        target_lang: str = "ta",
        hallucination_marker: str | None = None,
        **kwargs: Any,
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

        marker = hallucination_marker or self._HALLUCINATION_MARKER

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                retry=retry_if_result(lambda res: marker in str(res)),
            ):
                with attempt:
                    logger.info(
                        "vllm_translation_request",
                        model=self.model,
                        source=source_lang,
                        target=target_lang,
                        attempt=attempt.retry_state.attempt_number,
                    )

                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.post(
                            f"{self.base_url}/v1/chat/completions",
                            json=payload,
                        )
                        response.raise_for_status()

                    data = response.json()
                    last_text = data["choices"][0]["message"]["content"]

                    if marker not in last_text:
                        logger.debug(
                            "vllm_translation_ok",
                            length=len(last_text),
                            attempt=attempt.retry_state.attempt_number,
                        )
                    else:
                        logger.warning(
                            "vllm_translation_hallucination",
                            attempt=attempt.retry_state.attempt_number,
                            marker=marker,
                        )

                    return last_text
        except RetryError as e:
            logger.error(
                "vllm_translation_retries_exhausted",
                max_retries=self.max_retries,
            )
            val = e.last_attempt.result()
            return val if isinstance(val, str) else str(val)

        return ""
