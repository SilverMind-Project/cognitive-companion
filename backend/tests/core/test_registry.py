"""Tests for the generic PluginRegistry and HasMetadata base classes."""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.registry import HasMetadata, PluginRegistry


@dataclass
class _FakeMetadata:
    name: str
    description: str = ""


class _FakeHandler(HasMetadata[_FakeMetadata]):
    @classmethod
    def metadata(cls) -> _FakeMetadata:
        return _FakeMetadata(name="fake", description="A fake handler")


class _FakeHandler2(HasMetadata[_FakeMetadata]):
    @classmethod
    def metadata(cls) -> _FakeMetadata:
        return _FakeMetadata(name="fake2", description="Another fake handler")


class _FakeRegistry(PluginRegistry[_FakeHandler, _FakeMetadata]):
    _discovery_packages = ()

    @classmethod
    def _key_from_metadata(cls, meta: _FakeMetadata) -> str:
        return meta.name


class TestPluginRegistry:
    """Test the PluginRegistry generic base class directly."""

    def setup_method(self):
        _FakeRegistry._registry.clear()
        _FakeRegistry._instances.clear()

    def test_register_stores_class_and_instance(self):
        _FakeRegistry.register(_FakeHandler)
        assert _FakeRegistry.get("fake") is not None
        assert isinstance(_FakeRegistry.get("fake"), _FakeHandler)

    def test_get_missing_returns_none(self):
        assert _FakeRegistry.get("nonexistent") is None

    def test_all_names_returns_keys(self):
        _FakeRegistry.register(_FakeHandler)
        assert "fake" in _FakeRegistry.all_names()

    def test_all_metadata_returns_metadata_objects(self):
        _FakeRegistry.register(_FakeHandler)
        metas = _FakeRegistry.all_metadata()
        assert len(metas) == 1
        assert isinstance(metas[0], _FakeMetadata)
        assert metas[0].name == "fake"

    def test_multiple_registrations(self):
        _FakeRegistry.register(_FakeHandler)
        _FakeRegistry.register(_FakeHandler2)
        assert len(_FakeRegistry.all_names()) == 2
        assert _FakeRegistry.get("fake") is not None
        assert _FakeRegistry.get("fake2") is not None

    def test_register_can_be_used_as_decorator(self):
        @_FakeRegistry.register
        class _DecoratedHandler(_FakeHandler):
            @classmethod
            def metadata(cls) -> _FakeMetadata:
                return _FakeMetadata(name="decorated")

        assert _FakeRegistry.get("decorated") is not None


class TestRealRegistries:
    """Verify the three real registries work end-to-end."""

    def test_step_registry_discover_and_get(self):
        from backend.steps import StepRegistry

        if not StepRegistry.all_names():
            StepRegistry.discover()
        assert StepRegistry.get("wait") is not None

    def test_step_registry_get_class(self):
        from backend.steps import StepRegistry

        if not StepRegistry.all_names():
            StepRegistry.discover()
        cls = StepRegistry.get_class("wait")
        assert cls is not None
        from backend.steps.base import StepHandler

        assert issubclass(cls, StepHandler)

    def test_channel_registry_discover_and_get(self):
        from backend.channels import ChannelRegistry

        if not ChannelRegistry.all_names():
            ChannelRegistry.discover()
        assert ChannelRegistry.get("telegram") is not None

    def test_filter_registry_discover_and_get(self):
        from backend.filters import FilterRegistry

        if not FilterRegistry.all_names():
            FilterRegistry.discover()
        assert FilterRegistry.get("room") is not None

    def test_no_deprecated_aliases(self):
        from backend.channels import ChannelRegistry
        from backend.filters import FilterRegistry
        from backend.steps import StepRegistry

        for registry in (StepRegistry, ChannelRegistry, FilterRegistry):
            for method_name in dir(registry):
                method = getattr(registry, method_name)
                if callable(method) and hasattr(method, "__doc__") and method.__doc__:
                    assert "deprecated alias" not in method.__doc__, (
                        f"{registry.__name__}.{method_name} still has deprecated alias"
                    )
