"""Tests for :mod:`backend.core.auth`."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.core import auth as auth_module
from backend.core.auth import (
    ALLOWED_ACTIONS,
    AuthContext,
    KeyStore,
    _resolve_key,
    assert_declared_tokens_known,
    get_auth_context,
    get_auth_context_device,
    invalidate_lookup_cache,
    is_valid_d4_token,
    require_permission,
)
from backend.core.config import Settings
from backend.core.exceptions import AuthenticationError

# ─── KeyStore (pure) ──────────────────────────────────────────────────────


class TestKeyStoreResolve:
    def test_resolve_api_key(self) -> None:
        ks = KeyStore(
            api_keys=[{"key": "K1", "name": "admin", "roles": ["admin"]}],
            roles={"admin": ["*"]},
        )
        ctx = ks.resolve("K1")
        assert ctx.key == "K1"
        assert ctx.name == "admin"
        assert ctx.roles == ["admin"]
        assert ctx.device_type is None
        assert ctx.sensor_id is None

    def test_resolve_device_key_preferred_over_api(self) -> None:
        ks = KeyStore(
            api_keys=[{"key": "SHARED", "name": "api-ver", "roles": ["reader"]}],
            device_keys=[
                {
                    "key": "SHARED",
                    "name": "kitchen-cam",
                    "device_type": "camera",
                    "sensor_id": "cam-1",
                    "roles": ["device_recamera"],
                }
            ],
        )
        ctx = ks.resolve("SHARED")
        assert ctx.name == "kitchen-cam"
        assert ctx.roles == ["device_recamera"]
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


class TestKeyStoreTokens:
    def test_wildcard_role_allows_everything(self) -> None:
        ks = KeyStore(roles={"admin": ["*"]})
        auth = AuthContext(key="K", name="n", roles=["admin"])
        assert ks.has_token(auth, "rooms:read") is True
        assert ks.has_token(auth, "persons:delete") is True

    def test_role_token_membership(self) -> None:
        ks = KeyStore(roles={"caregiver": ["rooms:read", "sensors:read"]})
        auth = AuthContext(key="K", name="n", roles=["caregiver"])
        assert ks.has_token(auth, "rooms:read") is True
        assert ks.has_token(auth, "rooms:write") is False

    def test_multiple_roles_union_tokens(self) -> None:
        ks = KeyStore(
            roles={
                "mcp_readonly": ["mcp.tools:read", "rooms:read"],
                "mcp_rules_import": ["rules:import"],
            }
        )
        auth = AuthContext(key="K", name="n", roles=["mcp_readonly", "mcp_rules_import"])
        assert ks.has_token(auth, "rooms:read") is True
        assert ks.has_token(auth, "rules:import") is True
        assert ks.has_token(auth, "rules:execute") is False

    def test_unknown_role_grants_nothing(self) -> None:
        ks = KeyStore(roles={"caregiver": ["rooms:read"]})
        # Raw token string in roles: is NOT treated as a token grant.
        auth = AuthContext(key="K", name="n", roles=["rooms:read"])
        assert ks.has_token(auth, "rooms:read") is False

    def test_no_roles_denies_everything(self) -> None:
        ks = KeyStore(roles={"caregiver": ["rooms:read"]})
        auth = AuthContext(key="K", name="n", roles=[])
        assert ks.has_token(auth, "rooms:read") is False

    def test_direct_test_tokens_supported(self) -> None:
        ks = KeyStore()
        auth = AuthContext(key="K", name="n", tokens=frozenset({"visitors:review"}))
        assert ks.has_token(auth, "visitors:review") is True
        assert ks.has_token(auth, "rooms:read") is False


class TestKeyStoreFromSettings:
    def test_builds_from_settings_dict(self) -> None:
        s = Settings.from_dict(
            {
                "auth": {
                    "api_keys": [{"key": "K", "name": "n", "roles": ["reader"]}],
                    "device_keys": [{"key": "DEV", "name": "d", "roles": ["device"]}],
                    "roles": {
                        "reader": ["rooms:read"],
                        "device": ["device.recamera:ingest"],
                    },
                }
            }
        )
        ks = KeyStore.from_settings(s)
        ctx = ks.resolve("K")
        assert ctx.name == "n"
        assert ctx.roles == ["reader"]
        assert ks.has_token(ctx, "rooms:read") is True
        assert ks.has_token(ctx, "rooms:write") is False
        assert ks.resolve("DEV").name == "d"

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
            {"key": "ADMIN", "name": "admin", "roles": ["admin"]},
            {"key": "READER", "name": "reader", "roles": ["reader"]},
        ],
        device_keys=[{"key": "DEVICE01", "name": "cam", "sensor_id": "s1", "roles": ["device"]}],
        roles={
            "admin": ["*"],
            "reader": ["rooms:read"],
            "device": ["device.recamera:ingest"],
        },
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
        """Keys in query strings leak into access logs and browser history."""
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

    def test_reader_denied_on_non_rooms(self, stub_keystore: KeyStore) -> None:
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
        assert r.status_code == 401


# ─── Declared-token startup contract & D4 grammar ─────────────────────────


class TestAssertDeclaredTokensKnown:
    def test_unknown_d4_token_raises_and_names_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read", "totally:read"})
        ks = KeyStore(roles={"caregiver": ["rooms:read"]})
        with pytest.raises(RuntimeError, match="totally:read"):
            assert_declared_tokens_known(ks)

    def test_non_d4_declared_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"GET /api/v1/rooms"})
        ks = KeyStore(roles={"caregiver": ["rooms:read"]})
        with pytest.raises(RuntimeError, match="D4 grammar"):
            assert_declared_tokens_known(ks)

    def test_non_d4_configured_role_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read"})
        ks = KeyStore(roles={"caregiver": ["rooms:read", "wearables:manage"]})
        with pytest.raises(RuntimeError, match="wearables:manage"):
            assert_declared_tokens_known(ks)

    def test_unknown_key_role_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read"})
        ks = KeyStore(
            api_keys=[{"key": "K", "name": "BadKey", "roles": ["no_such_role"]}],
            roles={"caregiver": ["rooms:read"]},
        )
        with pytest.raises(RuntimeError, match="no_such_role"):
            assert_declared_tokens_known(ks)

    def test_known_d4_tokens_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", {"rooms:read"})
        ks = KeyStore(roles={"caregiver": ["rooms:read"]})
        assert_declared_tokens_known(ks)

    def test_declaring_a_token_registers_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set())
        require_permission("some:read")
        assert "some:read" in auth_module._DECLARED_TOKENS

    def test_d4_grammar_canary(self) -> None:
        assert is_valid_d4_token("rooms:read")
        assert is_valid_d4_token("cts.signals:acknowledge")
        assert not is_valid_d4_token("admin")
        assert not is_valid_d4_token("cts.cameras.read")
        assert not is_valid_d4_token("GET /api/v1/rooms")
        assert "manage" not in ALLOWED_ACTIONS


# ─── Checker marker + resolver plumbing ───────────────────────────────────


class TestCheckerMarker:
    @pytest.fixture(autouse=True)
    def _isolate_declared_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module, "_DECLARED_TOKENS", set())

    def test_factory_marks_checker_and_records_tokens(self) -> None:
        checker = require_permission("rooms:read")
        assert getattr(checker, "__cc_auth_checker__", False) is True
        assert checker.__cc_auth_tokens__ == ("rooms:read",)


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


# ─── Denial logging ───────────────────────────────────────────────────────


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
