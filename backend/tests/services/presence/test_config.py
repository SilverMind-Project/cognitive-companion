"""Tests for presence config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.services.presence.config import (
    CtsLocationProviderConfig,
    HaBedSensorProviderConfig,
    HaDeviceTrackerProviderConfig,
    PresenceConfig,
    load_presence_config,
)


def test_load_config_from_file(tmp_path: Path) -> None:
    """Round-trip the in-repo config format."""
    config_data = {
        "providers": [
            {
                "name": "cts_location",
                "ttl_seconds": 120,
                "confidence_floor": 0.0,
                "priority": 50,
            },
            {
                "name": "ha_bed_sensor",
                "entity_id": "binary_sensor.bed",
                "person_id": "mom",
                "room_id": "bedroom",
                "room_name": "Master Bedroom",
                "confidence": 0.95,
                "priority": 70,
            },
            {
                "name": "ha_device_tracker",
                "entity_id_template": "device_tracker.{person_id}_phone",
                "confidence": 0.8,
                "priority": 30,
            },
        ],
        "fusion": {
            "rule": "highest_priority_above_floor",
            "confidence_floor": 0.4,
        },
    }
    yaml_path = tmp_path / "presence.yaml"
    yaml_path.write_text(yaml.dump(config_data), encoding="utf-8")

    config = load_presence_config(yaml_path)
    assert isinstance(config, PresenceConfig)
    assert len(config.providers) == 3
    assert isinstance(config.providers[0], CtsLocationProviderConfig)
    assert isinstance(config.providers[1], HaBedSensorProviderConfig)
    assert isinstance(config.providers[2], HaDeviceTrackerProviderConfig)
    assert config.fusion.rule == "highest_priority_above_floor"
    assert config.fusion.confidence_floor == 0.4


def test_unknown_provider_rejects() -> None:
    """Reject a YAML with an unknown provider type."""
    config_data = {
        "providers": [
            {
                "name": "nonexistent_provider",
            },
        ],
    }
    yaml_path = Path("/tmp/test_presence.yaml")
    yaml_path.write_text(yaml.dump(config_data), encoding="utf-8")

    with pytest.raises(ValueError, match="nonexistent_provider"):
        load_presence_config(yaml_path)


def test_defaults_applied_when_fields_omitted() -> None:
    """Minimal provider config gets default values."""
    config_data = {
        "providers": [
            {"name": "cts_location"},
        ],
    }
    yaml_path = Path("/tmp/test_defaults.yaml")
    yaml_path.write_text(yaml.dump(config_data), encoding="utf-8")

    config = load_presence_config(yaml_path)
    cts = config.providers[0]
    assert isinstance(cts, CtsLocationProviderConfig)
    assert cts.ttl_seconds == 120
    assert cts.confidence_floor == 0.0
    assert cts.priority == 50


def test_ha_bed_sensor_defaults() -> None:
    """HaBedSensorProviderConfig gets defaults when fields omitted."""
    config_data = {
        "providers": [
            {
                "name": "ha_bed_sensor",
                "entity_id": "binary_sensor.bed",
                "person_id": "mom",
                "room_id": "bedroom",
            },
        ],
    }
    yaml_path = Path("/tmp/test_bed_defaults.yaml")
    yaml_path.write_text(yaml.dump(config_data), encoding="utf-8")

    config = load_presence_config(yaml_path)
    bed = config.providers[0]
    assert isinstance(bed, HaBedSensorProviderConfig)
    assert bed.room_name is None
    assert bed.confidence == 0.95
    assert bed.priority == 70
