"""Tests for the ServiceContainer boot-time completeness check (M13)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.services.container_wiring import (
    ALWAYS_REQUIRED,
    REQUIRED_WHEN,
    assert_container_complete,
)
from backend.steps.base import ServiceContainer


def _fully_populated_container() -> ServiceContainer:
    kwargs = {field: MagicMock() for field in ALWAYS_REQUIRED if field != "db_factory"}
    for fields in REQUIRED_WHEN.values():
        kwargs.update({field: MagicMock() for field in fields})
    return ServiceContainer(db_factory=MagicMock(), **kwargs)


def test_fully_populated_container_passes_with_all_features_enabled():
    container = _fully_populated_container()
    assert_container_complete(container, enabled=REQUIRED_WHEN.keys())


def test_fully_populated_container_passes_with_no_features_enabled():
    container = _fully_populated_container()
    assert_container_complete(container, enabled=[])


def test_always_required_field_missing_fails_even_with_no_features_enabled():
    container = ServiceContainer(db_factory=MagicMock())
    with pytest.raises(RuntimeError) as excinfo:
        assert_container_complete(container, enabled=[])
    for field in ALWAYS_REQUIRED - {"db_factory"}:
        assert field in str(excinfo.value)


@pytest.mark.parametrize("feature", sorted(REQUIRED_WHEN.keys()))
def test_missing_feature_gated_field_fails_when_feature_enabled(feature):
    container = _fully_populated_container()
    missing_field = next(iter(REQUIRED_WHEN[feature]))
    setattr(container, missing_field, None)

    with pytest.raises(RuntimeError) as excinfo:
        assert_container_complete(container, enabled=[feature])
    assert missing_field in str(excinfo.value)


@pytest.mark.parametrize("feature", sorted(REQUIRED_WHEN.keys()))
def test_missing_feature_gated_field_passes_when_feature_disabled(feature):
    container = _fully_populated_container()
    missing_field = next(iter(REQUIRED_WHEN[feature]))
    setattr(container, missing_field, None)

    assert_container_complete(container, enabled=[])
