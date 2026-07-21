"""Tests for :mod:`backend.core.auth`."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.core import auth as auth_module
from backend.core.auth import (
    AuthContext,
    KeyStore,
    _resolve_key,
    assert_declared_tokens_known,
    get_auth_context,
    get_auth_context_device,
    invalidate_lookup_cache,
    require_permission,
    require_token,
)
from backend.core.config import Settings
from backend.core.exceptions import AuthenticationError

# ─── KeyStore (pure) ──────────────────────────────────────────────────────


class TestKeyStoreResolve:
    def test_resolve_api_key(self) -> None:
        ks = KeyStore(
            api_keys=[{"key": "K1", "name": "admin", "permissions": ["*"]}],
        )
        ctx = ks.resolve("K1")
        assert ctx.key == "K1"
        assert ctx.name == "admin"
        assert ctx.permissions == ["*"]
        assert ctx.device_type is None
        assert ctx.sensor_id is None

    def test_resolve_device_key_preferred_over_api(self) -> None:
        # Same raw string appears in both lists: device wins.
        ks = KeyStore(
            api_keys=[{"key": "SHARED", "name": "api-ver"}],
            device_keys=[
                {
                    "key": "SHARED",
                    "name": "kitchen-cam",
                    "device_type": "camera",
                    "sensor_id": "cam-1",
                    "permissions": ["sensors:write"],
                }
            ],
        )
        ctx = ks.resolve("SHARED")
        assert ctx.name == "kitchen-cam"
        assert ctx.device_type == "camera"
        assert ctx.sensor_id == "cam-1"

    def test_device_default_name(self) -> None:
        ks = KeyStore(device_keys=[{"key": "ABCD1234"}])
        ctx = ks.resolve("ABCD1234")
        assert ctx.name == "Device ABCD1234"

    def test_api_default_name(self) -> None:
        ks = KeyStore(api_keys=[{"key": "K"}])
        ctx = ks.resolve("K")
        assert ctx.name == "API Key"

    def test_unknown_key_raises(self) -> None:
        ks = KeyStore(api_keys=[{"key": "K1"}])
        with pytest.raises(AuthenticationError):
            ks.resolve("mystery")

    def test_empty_store_raises(self) -> None:
        with pytest.raises(AuthenticationError):
            KeyStore().resolve("anything")


class TestKeyStorePermissions:
    def test_wildcard_allows_everything(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", permissions=["*"])
        assert ks.has_permission(auth, "GET", "/any/path") is True

    def test_literal_pattern_match(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", permissions=["GET /rooms"])
        assert ks.has_permission(auth, "GET", "/rooms") is True
        assert ks.has_permission(auth, "POST", "/rooms") is False

    def test_fnmatch_wildcard_in_pattern(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", permissions=["GET /rooms/*"])
        assert ks.has_permission(auth, "GET", "/rooms/42") is True
        assert ks.has_permission(auth, "GET", "/rooms") is False

    def test_permission_map_expansion(self) -> None:
        ks = KeyStore(
            permission_map={"rooms:read": ["GET /rooms", "GET /rooms/*"]},
        )
        auth = AuthContext(key="K", name="n", permissions=["rooms:read"])
        assert ks.has_permission(auth, "GET", "/rooms") is True
        assert ks.has_permission(auth, "GET", "/rooms/5") is True
        assert ks.has_permission(auth, "POST", "/rooms") is False

    def test_method_is_case_insensitive(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", permissions=["GET /x"])
        assert ks.has_permission(auth, "get", "/x") is True

    def test_no_permissions_denies_everything(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", permissions=[])
        assert ks.has_permission(auth, "GET", "/x") is False


class TestKeyStoreFromSettings:
    def test_builds_from_settings_dict(self) -> None:
        s = Settings.from_dict(
            {
                "auth": {
                    "api_keys": [{"key": "K", "name": "n", "permissions": ["*"]}],
                    "device_keys": [{"key": "DEV", "name": "d"}],
                    "permission_map": {"r:read": ["GET /r"]},
                }
            }
        )
        ks = KeyStore.from_settings(s)
        assert ks.resolve("K").name == "n"
        assert ks.resolve("DEV").name == "d"
        assert ks.expand_permissions(["r:read"]) == ["GET /r"]

    def test_empty_settings_produces_empty_store(self) -> None:
        ks = KeyStore.from_settings(Settings.from_dict({}))
        with pytest.raises(AuthenticationError):
            ks.resolve("x")


# ─── Module-level facade ──────────────────────────────────────────────────


@pytest.fixture
def stub_keystore(monkeypatch: pytest.MonkeyPatch) -> KeyStore:
    """Install a fresh KeyStore as the module-level default."""
    ks = KeyStore(
        api_keys=[
            {"key": "ADMIN", "name": "admin", "permissions": ["*"]},
            {"key": "READER", "name": "reader", "permissions": ["GET /rooms*"]},
        ],
        device_keys=[{"key": "DEVICE01", "name": "cam", "sensor_id": "s1"}],
    )
    monkeypatch.setattr(auth_module, "_default_keystore", ks)
    return ks


class TestInvalidateLookupCache:
    def test_clears_default(self, stub_keystore: KeyStore) -> None:
        assert auth_module._default_keystore is stub_keystore
        invalidate_lookup_cache()
        assert auth_module._default_keystore is None


class TestResolveKeyFacade:
    def test_module_level_resolve(self, stub_keystore: KeyStore) -> None:
        ctx = _resolve_key("ADMIN")
        assert ctx.name == "admin"

    def test_module_level_resolve_raises(self, stub_keystore: KeyStore) -> None:
        with pytest.raises(AuthenticationError):
            _resolve_key("nope")


# ─── FastAPI integration ──────────────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    from backend.core.exceptions import register_exception_handlers

    register_exception_handlers(app)

    @app.get("/rooms")
    async def list_rooms(auth: AuthContext = Depends(require_permission("rooms:read"))) -> dict:
        return {"as": auth.name}

    # Browser-facing surface: header only.
    @app.post("/rooms")
    async def create_room(auth: AuthContext = Depends(get_auth_context)) -> dict:
        return {"as": auth.name}

    # Device surface: opts into the permissive resolver.
    @app.post("/device/report")
    async def device_report(auth: AuthContext = Depends(get_auth_context_device)) -> dict:
        return {"device": auth.name, "sensor": auth.sensor_id}

    return app


class TestGetAuthContextIntegration:
    def test_header_key_accepted(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.get("/rooms", headers={"X-API-Key": "ADMIN"})
        assert r.status_code == 200
        assert r.json() == {"as": "admin"}

    def test_query_param_key_rejected_on_default_resolver(self, stub_keystore: KeyStore) -> None:
        """M16: keys in query strings leak into access logs and browser history."""
        client = TestClient(_make_app())
        r = client.get("/rooms?api_key=ADMIN")
        assert r.status_code == 401

    def test_body_key_rejected_on_default_resolver(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post("/rooms", json={"api_key": "ADMIN"})
        assert r.status_code == 401

    def test_missing_key_returns_401(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.get("/rooms")
        assert r.status_code == 401

    def test_unknown_key_returns_401(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.get("/rooms", headers={"X-API-Key": "UNKNOWN"})
        assert r.status_code == 401

    def test_reader_allowed_on_rooms(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.get("/rooms", headers={"X-API-Key": "READER"})
        assert r.status_code == 200

    def test_reader_denied_on_non_rooms(
        self, stub_keystore: KeyStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = FastAPI()
        from backend.core.exceptions import register_exception_handlers

        register_exception_handlers(app)

        @app.get("/secret")
        async def secret(
            auth: AuthContext = Depends(require_permission("secret:read")),
        ) -> dict:
            return {"ok": True}

        client = TestClient(app)
        r = client.get("/secret", headers={"X-API-Key": "READER"})
        assert r.status_code == 403

    def test_device_key_from_json_body(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post("/device/report", json={"device_key": "DEVICE01"})
        assert r.status_code == 200
        assert r.json() == {"device": "cam", "sensor": "s1"}

    def test_device_key_api_key_field_in_body(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post("/device/report", json={"api_key": "ADMIN"})
        assert r.status_code == 200

    def test_device_resolver_accepts_query_param(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post("/device/report?api_key=DEVICE01")
        assert r.status_code == 200

    def test_device_resolver_accepts_header(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post("/device/report", headers={"X-API-Key": "DEVICE01"})
        assert r.status_code == 200

    def test_device_resolver_prefers_header_over_query(self, stub_keystore: KeyStore) -> None:
        """Documented lookup order: header, then query, then body."""
        client = TestClient(_make_app())
        r = client.post("/device/report?api_key=ADMIN", headers={"X-API-Key": "DEVICE01"})
        assert r.status_code == 200
        assert r.json()["device"] == "cam"

    def test_malformed_json_body_does_not_crash(self, stub_keystore: KeyStore) -> None:
        client = TestClient(_make_app())
        r = client.post(
            "/device/report",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        # Missing key → 401, NOT 500.
        assert r.status_code == 401


# ─── Declared-token startup contract  ────────────────────────────────


class TestAssertDeclaredTokensKnown:
    def test_unknown_token_raises_and_names_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read", "totally:bogus"})
        ks = KeyStore(permission_map={"rooms:read": ["GET /rooms*"]})
        with pytest.raises(RuntimeError, match="totally:bogus"):
            assert_declared_tokens_known(ks)

    def test_known_tokens_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read"})
        ks = KeyStore(permission_map={"rooms:read": ["GET /rooms*"]})
        assert_declared_tokens_known(ks)  # does not raise

    def test_token_granted_only_as_a_role_value_is_known(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """auth.yaml grants require_token names as role values, not map keys."""
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"cts.view"})
        ks = KeyStore(permission_map={"caregiver": ["cts.view"]})
        assert_declared_tokens_known(ks)

    def test_literal_path_patterns_need_no_definition(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"GET /api/v1/rooms"})
        assert_declared_tokens_known(KeyStore(permission_map={}))

    def test_declaring_a_token_registers_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set())
        require_permission("some:token")
        require_token("other:token")
        assert {"some:token", "other:token"} <= auth_module._DECLARED_TOKENS


# ─── Checker marker + resolver plumbing  ─────────────────────────────


class TestCheckerMarker:
    """_DECLARED_TOKENS is process-global: isolate it so declaring throwaway
    tokens here cannot leak into the real-app startup contract asserted by
    tests/routers/test_route_auth_coverage.py."""

    @pytest.fixture(autouse=True)
    def _isolate_declared_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set())

    def test_both_factories_mark_their_checker(self) -> None:
        for checker in (require_permission("rooms:read"), require_token("rooms:read")):
            assert getattr(checker, "__cc_auth_checker__", False) is True

    def test_marker_records_declared_tokens(self) -> None:
        checker = require_permission("a:b", "c:d")
        assert checker.__cc_auth_tokens__ == ("a:b", "c:d")
        assert checker.__cc_auth_kind__ == "permission"


class TestResolverPlumbing:
    def _app(self, dep) -> FastAPI:
        app = FastAPI()
        from backend.core.exceptions import register_exception_handlers

        register_exception_handlers(app)

        @app.post("/thing")
        async def thing(auth: AuthContext = Depends(dep)) -> dict:
            return {"as": auth.name}

        return app

    def test_require_permission_default_resolver_rejects_query(
        self, stub_keystore: KeyStore
    ) -> None:
        client = TestClient(self._app(require_permission("rooms:read")))
        assert client.post("/thing?api_key=ADMIN").status_code == 401

    def test_require_permission_device_resolver_accepts_query(
        self, stub_keystore: KeyStore
    ) -> None:
        dep = require_permission("rooms:read", resolver=get_auth_context_device)
        client = TestClient(self._app(dep))
        assert client.post("/thing?api_key=ADMIN").status_code == 200

    def test_require_token_device_resolver_accepts_query(self, stub_keystore: KeyStore) -> None:
        dep = require_token("*", resolver=get_auth_context_device)
        client = TestClient(self._app(dep))
        assert client.post("/thing?api_key=ADMIN").status_code == 200


# ─── Denial logging  ─────────────────────────────────────────────────


class TestAuthDeniedLogging:
    def test_unknown_key_logs_without_key_material(
        self, stub_keystore: KeyStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = TestClient(_make_app())
        with caplog.at_level("INFO"):
            client.get("/rooms", headers={"X-API-Key": "SUPERSECRET"})
        records = [r for r in caplog.records if "auth_denied" in r.getMessage()]
        assert records, "expected an auth_denied event"
        assert "SUPERSECRET" not in caplog.text

    def test_permission_denial_logs_reason(
        self, stub_keystore: KeyStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        app = FastAPI()
        from backend.core.exceptions import register_exception_handlers

        register_exception_handlers(app)

        @app.get("/secret")
        async def secret(_a: AuthContext = Depends(require_permission("secret:read"))) -> dict:
            return {}

        with caplog.at_level("INFO"):
            r = TestClient(app).get("/secret", headers={"X-API-Key": "READER"})
        assert r.status_code == 403
        assert "auth_denied" in caplog.text
        assert "READER" not in caplog.text
