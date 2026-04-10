"""Unit tests for ``RAGService``.

Each test monkeypatches ``backend.services.rag.settings`` to a small fake
object with a ``.get()`` method so we can construct a service with a known
configuration without touching process-global state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.services import rag as rag_module
from backend.services.rag import RAGService


class _FakeSettings:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)


@pytest.fixture
def rag_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Return a helper that installs a fake ``settings`` and returns a fresh
    ``RAGService`` bound to ``tmp_path``.
    """

    def _make(**overrides: Any) -> RAGService:
        values = {
            "rag.enabled": True,
            "rag.index_path": str(tmp_path),
            "rag.threshold": 0.5,
            "rag.max_results": 3,
        }
        values.update(overrides)
        monkeypatch.setattr(rag_module, "settings", _FakeSettings(values))
        return RAGService()

    return _make


# ---------------------------------------------------------------------------
# Construction & config
# ---------------------------------------------------------------------------


def test_defaults_when_settings_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag_module, "settings", _FakeSettings({}))
    service = RAGService()
    assert service.enabled is False
    assert service.index_path == Path("data/rag_index")
    assert service.threshold == 0.7
    assert service.max_results == 5
    assert service._documents == []
    assert service._loaded is False


def test_construction_respects_overrides(rag_settings) -> None:
    service = rag_settings(**{"rag.threshold": 0.42, "rag.max_results": 7})
    assert service.enabled is True
    assert service.threshold == 0.42
    assert service.max_results == 7


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------


def test_load_noop_when_disabled(rag_settings) -> None:
    service = rag_settings(**{"rag.enabled": False})
    service.load()
    assert service._loaded is False


def test_load_noop_when_index_missing(rag_settings, tmp_path: Path) -> None:
    service = rag_settings()
    assert not (tmp_path / "documents.json").exists()
    service.load()
    assert service._loaded is False
    assert service._documents == []


def test_load_reads_documents(rag_settings, tmp_path: Path) -> None:
    docs = [
        {"content": "kitchen safety tips", "metadata": {}},
        {"content": "medication reminders", "metadata": {}},
    ]
    (tmp_path / "documents.json").write_text(json.dumps(docs))
    service = rag_settings()
    service.load()
    assert service._loaded is True
    assert len(service._documents) == 2


def test_load_handles_bad_json(rag_settings, tmp_path: Path) -> None:
    (tmp_path / "documents.json").write_text("not valid json {")
    service = rag_settings()
    service.load()  # must not raise
    assert service._loaded is False


# ---------------------------------------------------------------------------
# lookup()
# ---------------------------------------------------------------------------


class TestLookup:
    def test_disabled_returns_empty(self, rag_settings) -> None:
        service = rag_settings(**{"rag.enabled": False})
        assert service.lookup("anything") == ""

    def test_not_loaded_returns_empty(self, rag_settings) -> None:
        service = rag_settings()
        assert service.lookup("anything") == ""

    def test_empty_documents_returns_empty(self, rag_settings) -> None:
        service = rag_settings()
        service._loaded = True
        service._documents = []
        assert service.lookup("anything") == ""

    def test_match_above_threshold(self, rag_settings) -> None:
        service = rag_settings(**{"rag.threshold": 0.4})
        service._loaded = True
        service._documents = [
            {"content": "the kitchen is on fire", "metadata": {}},
        ]
        result = service.lookup("kitchen fire")
        assert "kitchen" in result

    def test_below_threshold_returns_empty(self, rag_settings) -> None:
        service = rag_settings(**{"rag.threshold": 0.99})
        service._loaded = True
        service._documents = [{"content": "medication", "metadata": {}}]
        assert service.lookup("unrelated query terms") == ""

    def test_max_results_cap(self, rag_settings) -> None:
        service = rag_settings(**{"rag.threshold": 0.1, "rag.max_results": 2})
        service._loaded = True
        service._documents = [
            {"content": f"apple doc{i}", "metadata": {}} for i in range(5)
        ]
        result = service.lookup("apple")
        # Separator count = max_results - 1 = 1
        assert result.count("---") == 1

    def test_scores_sorted_descending(self, rag_settings) -> None:
        service = rag_settings(**{"rag.threshold": 0.0, "rag.max_results": 3})
        service._loaded = True
        service._documents = [
            {"content": "banana", "metadata": {}},
            {"content": "apple apple apple", "metadata": {}},
            {"content": "apple banana", "metadata": {}},
        ]
        # Query "apple": doc "apple apple apple" and "apple banana" both
        # overlap; the exact order depends on set semantics but the apple
        # docs should appear before "banana"-only.
        result = service.lookup("apple")
        assert "apple" in result.split("\n---\n")[0]

    def test_empty_doc_content_skipped(self, rag_settings) -> None:
        service = rag_settings(**{"rag.threshold": 0.1})
        service._loaded = True
        service._documents = [{"content": "", "metadata": {}}]
        assert service.lookup("anything") == ""


# ---------------------------------------------------------------------------
# add_document() and save()
# ---------------------------------------------------------------------------


def test_add_document_appends(rag_settings) -> None:
    service = rag_settings()
    service.add_document("hello")
    service.add_document("world", metadata={"source": "test"})
    assert len(service._documents) == 2
    assert service._documents[0] == {"content": "hello", "metadata": {}}
    assert service._documents[1]["metadata"] == {"source": "test"}


def test_save_creates_dir_and_writes(rag_settings, tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "index"
    import shutil

    if nested.exists():
        shutil.rmtree(nested)

    from backend.services import rag as rag_module_inner

    rag_module_inner.settings = _FakeSettings(  # type: ignore[attr-defined]
        {
            "rag.enabled": True,
            "rag.index_path": str(nested),
            "rag.threshold": 0.5,
            "rag.max_results": 3,
        }
    )
    service = RAGService()
    service.add_document("persisted")
    service.save()

    docs_file = nested / "documents.json"
    assert docs_file.exists()
    loaded = json.loads(docs_file.read_text())
    assert loaded[0]["content"] == "persisted"


def test_save_roundtrip(rag_settings, tmp_path: Path) -> None:
    service1 = rag_settings()
    service1.add_document("first")
    service1.add_document("second")
    service1.save()

    service2 = rag_settings()
    service2.load()
    assert len(service2._documents) == 2
    assert {d["content"] for d in service2._documents} == {"first", "second"}
