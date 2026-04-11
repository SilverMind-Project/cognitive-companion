"""
OpenAI-compatible LLM provider for vLLM, llama.cpp llama-server, and similar.

Works with any server that exposes a ``/v1/chat/completions`` endpoint.

Guided decoding:
  - ``guided_decoding=True`` (vLLM): injects ``guided_json`` in the payload.
  - ``guided_decoding=False`` (llama.cpp etc.): appends schema as a prompt
    instruction so the model understands the expected format.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from tenacity import AsyncRetrying, RetryError, retry_if_result, stop_after_attempt

from backend.core.logging import get_logger
from backend.integrations.llm.base import THINKING_INSTRUCTION, LLMProvider, strip_thinking

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = 120.0


def _encode_image_data_uri(path: str) -> str:
    """Read an image file and return a ``data:<mime>;base64,...`` URI."""
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/jpeg"
    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    return f"data:{mime};base64,{b64}"


class OpenAICompatibleProvider(LLMProvider):
    """
    Calls any OpenAI-compatible ``/v1/chat/completions`` endpoint.

    Supports images (base64 inline), JSON schema enforcement, and
    hallucination-retry via tenacity.

    Parameters
    ----------
    base_url:
        Base URL of the server (e.g. ``http://192.168.1.31:8100``).
    model:
        Model name to pass in the request payload.
    max_tokens:
        Maximum tokens to generate.
    timeout:
        HTTP request timeout in seconds.
    guided_decoding:
        When ``True``, pass ``guided_json`` in the payload (vLLM).
        When ``False``, append the schema as a prompt instruction (llama.cpp).
    max_retries:
        Number of retries when a hallucination marker is detected.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        max_tokens: int = 4096,
        timeout: float = _DEFAULT_TIMEOUT,
        guided_decoding: bool = False,
        max_retries: int = 3,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.guided_decoding = guided_decoding
        self.max_retries = max_retries
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
        *,
        hallucination_marker: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a prompt (and optional images) to the model and return the
        text response.

        Parameters
        ----------
        prompt:
            User prompt text.
        media_paths:
            Optional list of image (or video) file paths to attach.
        media_type:
            ``"image"`` or ``"video"``.  For video, frames are extracted
            first via :func:`backend.services.media_processor.extract_frames`.
        response_schema:
            JSON Schema dict.  Enforced via ``guided_json`` (vLLM) or prompt
            injection (other servers).
        hallucination_marker:
            If the response contains this string the call is retried up to
            ``max_retries`` times.
        """
        content: list[dict[str, Any]] = []

        # -- Attach media -------------------------------------------------------
        if media_paths:
            if media_type == "video":
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
                for img in media_paths:
                    data_uri = _encode_image_data_uri(img)
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        }
                    )

        # Text prompt comes last so the model sees images before the question.
        effective_prompt = prompt
        if response_schema and not self.guided_decoding:
            schema_str = json.dumps(response_schema, indent=2)
            effective_prompt = (
                prompt + f"\n\nRespond with valid JSON matching this schema:\n{schema_str}"
            )
        content.append({"type": "text", "text": effective_prompt})

        # Chain-of-thought instruction appended after the prompt.
        if thinking:
            content.append({"type": "text", "text": THINKING_INSTRUCTION})

        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]

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

        # vLLM guided decoding
        if response_schema and self.guided_decoding:
            payload["guided_json"] = response_schema

        logger.info(
            "openai_compat_request",
            model=self.model,
            num_images=sum(1 for c in content if c["type"] == "image_url"),
            guided=self.guided_decoding and response_schema is not None,
        )

        async def _call_once() -> str:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
            data = resp.json()
            text: str = data["choices"][0]["message"]["content"] or ""
            if thinking:
                text = strip_thinking(text)
            logger.debug("openai_compat_response", length=len(text))
            return text

        if not hallucination_marker:
            return await _call_once()

        # Retry on hallucination marker
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                retry=retry_if_result(lambda res: hallucination_marker in str(res)),
            ):
                with attempt:
                    logger.info(
                        "openai_compat_attempt",
                        attempt=attempt.retry_state.attempt_number,
                    )
                    text = await _call_once()
                    if hallucination_marker in text:
                        logger.warning(
                            "openai_compat_hallucination",
                            marker=hallucination_marker,
                            attempt=attempt.retry_state.attempt_number,
                        )
                    return text
        except RetryError as exc:
            logger.error("openai_compat_retries_exhausted", max_retries=self.max_retries)
            val = exc.last_attempt.result()
            return val if isinstance(val, str) else str(val)

        return ""
