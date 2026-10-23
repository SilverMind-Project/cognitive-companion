from __future__ import annotations

import pytest

from backend.main import app
from backend.scripts.export_openapi import CONTRACT_DOCUMENT_VERSION, build_spec, render


def test_export_does_not_change_across_a_version_bump(monkeypatch: pytest.MonkeyPatch):
    """The version-bump git hook changes the app version on every commit to main; the
    committed contract must not, or the CI drift gate fails after every commit."""
    before = render(build_spec())

    monkeypatch.setattr(app, "version", "999.0.0")
    monkeypatch.setattr(app, "openapi_schema", None)
    after = render(build_spec())

    assert after == before
    assert '"999.0.0"' not in after


def test_export_pins_the_document_version():
    assert build_spec()["info"]["version"] == CONTRACT_DOCUMENT_VERSION


def test_export_leaves_the_served_schema_untouched():
    build_spec()

    assert app.openapi()["info"]["version"] == app.version
