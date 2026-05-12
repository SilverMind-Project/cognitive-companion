"""Tests for the plugin migration infrastructure."""

import pytest

from backend.core.plugin_migrations import ConfigMigration, migrate_config


def _add_field_v1_to_v2(config: dict) -> dict:
    result = dict(config)
    result["new_field"] = "default_value"
    return result


def _rename_field_v2_to_v3(config: dict) -> dict:
    result = dict(config)
    result["renamed_field"] = result.pop("old_field", None)
    return result


_MIGRATIONS = (
    ConfigMigration(
        from_version=1, to_version=2,
        description="Add new_field default",
        apply=_add_field_v1_to_v2,
    ),
    ConfigMigration(
        from_version=2, to_version=3,
        description="Rename old_field to renamed_field",
        apply=_rename_field_v2_to_v3,
    ),
)


class TestMigrateConfig:
    def test_noop_when_versions_equal(self):
        config = {"key": "value"}
        result = migrate_config(config, _MIGRATIONS, from_version=1, to_version=1)
        assert result == {"key": "value"}
        assert result is not config  # Always returns a new dict

    def test_single_migration(self):
        config = {"old_field": "data"}
        result = migrate_config(config, _MIGRATIONS, from_version=1, to_version=2)
        assert result == {"old_field": "data", "new_field": "default_value"}

    def test_chain_migration(self):
        config = {"old_field": "data"}
        result = migrate_config(config, _MIGRATIONS, from_version=1, to_version=3)
        assert result == {
            "new_field": "default_value",
            "renamed_field": "data",
        }

    def test_raises_when_migration_missing(self):
        config = {"key": "value"}
        with pytest.raises(ValueError, match="No migration from v3 to v4"):
            migrate_config(config, _MIGRATIONS, from_version=1, to_version=5)

    def test_does_not_mutate_input(self):
        config = {"old_field": "original"}
        _ = migrate_config(config, _MIGRATIONS, from_version=1, to_version=2)
        assert config == {"old_field": "original"}
