"""Tests for :mod:`backend.core.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.config import (
    DEFAULT_CONFIG_DIR,
    ConfigFileNotFoundError,
    SettingNotFoundError,
    Settings,
    SettingTypeError,
)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Write a minimal but representative YAML config tree and return its path."""
    (tmp_path / "settings.yaml").write_text(
        """
app:
  log_level: INFO
  name: ${APP_NAME}
database:
  url: postgresql+psycopg://cc:cc@localhost:5432/cc_test
llm:
  vision:
    model: fake-vision
    endpoint: ${LLM_ENDPOINT}
"""
    )
    (tmp_path / "auth.yaml").write_text(
        """
api_keys:
  - key: KEY1
    name: admin
    permissions:
      - "*"
permission_map:
  rooms:read:
    - GET /rooms
"""
    )
    (tmp_path / "notifications.yaml").write_text(
        """
channels:
  - name: telegram
    enabled: true
"""
    )
    return tmp_path


class TestFromDict:
    def test_direct_access(self) -> None:
        s = Settings.from_dict({"a": {"b": 1}})
        assert s.get("a.b") == 1

    def test_missing_default(self) -> None:
        s = Settings.from_dict({})
        assert s.get("x.y", default="fallback") == "fallback"

    def test_no_disk_io(self, tmp_path: Path) -> None:
        # from_dict should mark loaded=True so get() never touches the fs.
        s = Settings.from_dict({"k": "v"})
        # Point config_dir at a non-existent path to prove we don't read it.
        s._config_dir = tmp_path / "does-not-exist"
        assert s.get("k") == "v"

    def test_get_required_returns_value(self) -> None:
        s = Settings.from_dict({"a": {"b": 1}})
        assert s.get_required("a.b") == 1

    def test_get_required_raises_for_missing_nested_key(self) -> None:
        s = Settings.from_dict({"a": {"b": 1}})
        with pytest.raises(SettingNotFoundError, match=r"a\.c"):
            s.get_required("a.c")


class TestTypedAccessors:
    def test_scalar_accessors_return_typed_values(self) -> None:
        s = Settings.from_dict({"a": {"name": "cc", "count": 3, "ratio": 0.5, "enabled": True}})

        assert s.as_str("a.name") == "cc"
        assert s.as_int("a.count") == 3
        assert s.as_float("a.ratio") == 0.5
        assert s.as_bool("a.enabled") is True

    def test_section_accessors_are_relative_to_prefix(self) -> None:
        s = Settings.from_dict({"memory_query": {"cache": {"enabled": True, "ttl_seconds": 30}}})
        cache = s.section("memory_query.cache")

        assert cache.as_bool("enabled") is True
        assert cache.as_int("ttl_seconds") == 30

    def test_wrong_type_raises_with_key_name(self) -> None:
        s = Settings.from_dict({"a": {"count": "3"}})

        with pytest.raises(SettingTypeError, match=r"a\.count"):
            s.as_int("a.count")

    def test_non_empty_string_rejects_empty_value(self) -> None:
        s = Settings.from_dict({"service": {"url": ""}})

        with pytest.raises(SettingNotFoundError, match=r"service\.url"):
            s.as_str("service.url", allow_empty=False)


class TestLoadFromYaml:
    def test_basic_get(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s.get("app.log_level") == "INFO"
        assert s.get("database.url") == "postgresql+psycopg://cc:cc@localhost:5432/cc_test"

    def test_missing_returns_default(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s.get("nonexistent.key", default=7) == 7

    def test_auth_namespaced_under_auth_key(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s.get("auth.api_keys")[0]["key"] == "KEY1"
        assert s.get("auth.permission_map.rooms:read") == ["GET /rooms"]

    def test_notifications_namespaced(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        channels = s.get("notifications.channels")
        assert isinstance(channels, list)
        assert channels[0]["name"] == "telegram"


class TestEnvInterpolation:
    def test_substitutes_defined_env_var(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={"APP_NAME": "CognitiveCompanion"})
        assert s.get("app.name") == "CognitiveCompanion"

    def test_missing_env_becomes_empty_string(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s.get("app.name") == ""

    def test_interpolation_runs_inside_nested_structures(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={"LLM_ENDPOINT": "https://example.test"})
        assert s.get("llm.vision.endpoint") == "https://example.test"


class TestMissingFiles:
    def test_missing_yaml_files_raise(self, tmp_path: Path) -> None:
        s = Settings(config_dir=tmp_path, env={})

        with pytest.raises(ConfigFileNotFoundError):
            s.raw()

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text("")
        (tmp_path / "auth.yaml").write_text("")
        (tmp_path / "notifications.yaml").write_text("")
        s = Settings(config_dir=tmp_path, env={})
        assert s.raw() == {"auth": {}, "notifications": {}}


class TestReload:
    def test_reload_picks_up_changes(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s.get("app.log_level") == "INFO"

        (config_dir / "settings.yaml").write_text("app:\n  log_level: DEBUG\n")
        s.reload()
        assert s.get("app.log_level") == "DEBUG"

    def test_reload_accepts_different_dir(self, tmp_path: Path, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        s.reload()
        assert s.get("app.log_level") == "INFO"

        other = tmp_path / "other"
        other.mkdir()
        (other / "settings.yaml").write_text("app:\n  log_level: ERROR\n")
        (other / "auth.yaml").write_text("")
        (other / "notifications.yaml").write_text("")
        s.reload(config_dir=other)
        assert s.get("app.log_level") == "ERROR"
        assert s.config_dir == other


class TestDunderSugar:
    def test_getitem(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s["app.log_level"] == "INFO"

    def test_getitem_raises_for_missing_key(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        with pytest.raises(SettingNotFoundError, match=r"nope\.nada"):
            _ = s["nope.nada"]

    def test_contains_true_for_existing_key(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert "app.log_level" in s

    def test_contains_false_for_missing_key(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert "nope.nada" not in s


class TestLaziness:
    def test_get_triggers_load_on_first_access(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s._loaded is False
        _ = s.get("app.log_level")
        assert s._loaded is True

    def test_raw_triggers_load(self, config_dir: Path) -> None:
        s = Settings(config_dir=config_dir, env={})
        assert s._loaded is False
        s.raw()
        assert s._loaded is True


class TestDefaults:
    def test_default_config_dir_points_at_repo_config(self) -> None:
        # The default dir should be ``<repo>/config`` and at minimum contain
        # the three canonical files in a working checkout.
        assert DEFAULT_CONFIG_DIR.name == "config"
        # We don't assert file existence here: tests must run in envs without
        # the YAML files present.
