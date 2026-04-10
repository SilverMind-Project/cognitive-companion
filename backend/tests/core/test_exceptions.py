"""Tests for :mod:`backend.core.exceptions`."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    register_exception_handlers,
)


class TestAppError:
    def test_default_status_code_is_500(self) -> None:
        err = AppError("boom")
        assert err.status_code == 500
        assert err.message == "boom"
        assert str(err) == "boom"

    def test_custom_status_code(self) -> None:
        err = AppError("teapot", status_code=418)
        assert err.status_code == 418

    def test_is_exception_subclass(self) -> None:
        assert issubclass(AppError, Exception)
        with pytest.raises(AppError):
            raise AppError("x")


class TestConcreteErrors:
    def test_not_found_formats_identifier(self) -> None:
        err = NotFoundError("Room", 42)
        assert err.status_code == 404
        assert "Room" in err.message
        assert "42" in err.message

    def test_not_found_accepts_string_id(self) -> None:
        err = NotFoundError("User", "alice")
        assert "alice" in err.message

    def test_conflict_error(self) -> None:
        err = ConflictError("duplicate key")
        assert err.status_code == 409
        assert err.message == "duplicate key"

    def test_authentication_error_defaults(self) -> None:
        err = AuthenticationError()
        assert err.status_code == 401
        assert "API key" in err.message

    def test_authentication_error_custom_message(self) -> None:
        err = AuthenticationError("token expired")
        assert err.message == "token expired"

    def test_permission_denied_defaults(self) -> None:
        err = PermissionDeniedError()
        assert err.status_code == 403

    def test_validation_error(self) -> None:
        err = ValidationError("bad field")
        assert err.status_code == 422

    def test_all_inherit_from_app_error(self) -> None:
        for cls in (
            NotFoundError,
            ConflictError,
            AuthenticationError,
            PermissionDeniedError,
            ValidationError,
        ):
            assert issubclass(cls, AppError)


class TestRegisterExceptionHandlers:
    def _make_app(self) -> FastAPI:
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/boom")
        def boom() -> None:
            raise AppError("generic boom", status_code=500)

        @app.get("/missing")
        def missing() -> None:
            raise NotFoundError("Widget", 7)

        @app.get("/forbidden")
        def forbidden() -> None:
            raise PermissionDeniedError()

        return app

    def test_generic_app_error_rendered_as_json(self) -> None:
        client = TestClient(self._make_app())
        resp = client.get("/boom")
        assert resp.status_code == 500
        assert resp.json() == {"error": "generic boom"}

    def test_not_found_rendered_with_404(self) -> None:
        client = TestClient(self._make_app())
        resp = client.get("/missing")
        assert resp.status_code == 404
        assert "Widget" in resp.json()["error"]
        assert "7" in resp.json()["error"]

    def test_permission_denied_rendered_with_403(self) -> None:
        client = TestClient(self._make_app())
        resp = client.get("/forbidden")
        assert resp.status_code == 403
