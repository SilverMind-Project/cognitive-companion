"""Unit tests for the llm_models_health endpoint in backend.routers.admin.

Covers:
- Success path: configured model found in /v1/models response
- Warning path: configured model absent from /v1/models response
- Error path (connection): httpx.ConnectError raised
- Error path (timeout): httpx.TimeoutException raised
- Empty config: settings.get("llm.models") returns []
- Timeout value: httpx.AsyncClient is constructed with timeout=10.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.routers.admin import llm_models_health

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL_CFG = {
    "id": "test_model",
    "name": "Test Model",
    "base_url": "http://inference.local",
    "model": "vendor/test-model-7b",
}


def _make_response(model_ids: list[str]) -> MagicMock:
    """Build a mock httpx.Response whose .json() returns an OpenAI-style models list."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"data": [{"id": mid} for mid in model_ids]}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLlmModelsHealthSuccess:
    async def test_status_is_success_when_model_present(self):
        """Success path: configured model found in /v1/models → status == 'success'."""
        mock_resp = _make_response(["vendor/test-model-7b", "other/model"])

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        assert len(result) == 1
        item = result[0]
        assert item["status"] == "success"

    async def test_required_fields_present_on_success(self):
        """Required fields id, name, configured_model are always present."""
        mock_resp = _make_response(["vendor/test-model-7b"])

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        item = result[0]
        assert item["id"] == "test_model"
        assert item["name"] == "Test Model"
        assert item["configured_model"] == "vendor/test-model-7b"


class TestLlmModelsHealthWarning:
    async def test_status_is_warning_when_model_absent(self):
        """Warning path: model not in /v1/models list → status == 'warning'."""
        mock_resp = _make_response(["other/model-a", "other/model-b"])

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        item = result[0]
        assert item["status"] == "warning"

    async def test_warning_detail_contains_configured_model(self):
        """Warning detail must mention the configured model name."""
        mock_resp = _make_response(["other/model-a"])

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        detail = result[0]["detail"]
        assert "vendor/test-model-7b" in detail

    async def test_warning_detail_contains_available_ids(self):
        """Warning detail must mention the available model IDs."""
        mock_resp = _make_response(["other/model-a", "other/model-b"])

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        detail = result[0]["detail"]
        assert "other/model-a" in detail
        assert "other/model-b" in detail


class TestLlmModelsHealthError:
    async def test_connect_error_yields_error_status(self):
        """Error path (connection): ConnectError → status == 'error'."""
        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        item = result[0]
        assert item["status"] == "error"

    async def test_connect_error_detail_is_non_empty(self):
        """Error path (connection): detail field must be a non-empty string."""
        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        assert result[0].get("detail")

    async def test_timeout_exception_yields_error_status(self):
        """Error path (timeout): TimeoutException → status == 'error'."""
        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        assert result[0]["status"] == "error"

    async def test_required_fields_present_on_error(self):
        """id, name, configured_model are present even when status is error."""
        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("refused")
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await llm_models_health()

        item = result[0]
        assert item["id"] == "test_model"
        assert item["name"] == "Test Model"
        assert item["configured_model"] == "vendor/test-model-7b"


class TestLlmModelsHealthEmptyConfig:
    async def test_empty_models_list_returns_empty_array(self):
        """Empty config: settings returns [] → endpoint returns []."""
        with patch("backend.routers.admin.settings") as mock_settings:
            mock_settings.get.return_value = []
            result = await llm_models_health()

        assert result == []

    async def test_none_models_returns_empty_array(self):
        """None config (absent key): settings returns None → endpoint returns []."""
        with patch("backend.routers.admin.settings") as mock_settings:
            mock_settings.get.return_value = None
            result = await llm_models_health()

        assert result == []


class TestLlmModelsHealthTimeoutValue:
    async def test_httpx_client_timeout_is_10_seconds(self):
        """httpx.AsyncClient must be constructed with timeout=10.0."""
        mock_resp = _make_response(["vendor/test-model-7b"])
        captured_kwargs: dict = {}

        original_init = httpx.AsyncClient.__init__

        def _capturing_init(self, *args, **kwargs):
            captured_kwargs.update(kwargs)
            original_init(self, *args, **kwargs)

        with (
            patch("backend.routers.admin.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.get.return_value = [_MODEL_CFG]
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await llm_models_health()

            # Verify the AsyncClient was called with timeout=10.0
            mock_client_cls.assert_called_once_with(timeout=10.0)
