"""EG-M14 PR 3 inverse-shadow evaluation tests and full access-matrix replay."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.core import auth as auth_module
from backend.core.auth import (
    AuthContext,
    KeyStore,
    cc_auth_shadow_mismatch_total,
    evaluate_ws_inverse_shadow,
    require_permission,
    require_token,
)
from backend.core.config import Settings
from backend.core.permission_migration import (
    D4_TO_LEGACY_REQUIRE_TOKEN,
    M14T_CONSOLIDATION_DELTAS,
    MCP_READONLY_TWIN_TOKENS,
    ROLE_TO_LEGACY_PERMISSIONS,
)
from backend.scripts.export_route_permissions import AUTH_YAML_PATH, collect_route_inventory

_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")


def _real_keystore() -> KeyStore:
    data = yaml.safe_load(Path(AUTH_YAML_PATH).read_text(encoding="utf-8"))
    return KeyStore(
        api_keys=data.get("api_keys", []),
        device_keys=data.get("device_keys", []),
        permission_map=data.get("permission_map", {}),
        roles=data.get("roles", {}),
    )


def test_dual_evaluator_replay_matches_entire_access_matrix_except_approved_deltas() -> None:
    """Replay every guarded HTTP route + WS route across every configured role.

    Live PR 3 D4 ``roles:`` token evaluation and legacy path-glob / ``require_token``
    inverse-shadow evaluation must agree on every cell except:
    - the 4 ``M14T_CONSOLIDATION_DELTAS``; and
    - ``mcp_readonly`` pure ``:read`` HTTP routes whose D4 token is shared with an
      MCP read tool twin (PR 3 router-twin parity).
    """
    ks = _real_keystore()
    rows = collect_route_inventory()
    expected_m14t = {
        (d.role, d.method, d.path): (d.proposed, d.today) for d in M14T_CONSOLIDATION_DELTAS
    }

    checked_cells = 0
    unexpected_deltas: dict[tuple[str, str, str], tuple[bool, bool]] = {}
    observed_m14t: dict[tuple[str, str, str], tuple[bool, bool]] = {}

    for row in rows:
        concrete_path = _PATH_PARAM_RE.sub("sample", row.path)
        for role, legacy_perms in ROLE_TO_LEGACY_PERMISSIONS.items():
            auth = AuthContext(
                key="replay-key",
                name=role,
                permissions=list(legacy_perms),
                roles=[role],
            )
            live_allowed = ks.has_role_token(auth, row.proposed_token)

            if row.auth_kind == "token":
                legacy_tok = D4_TO_LEGACY_REQUIRE_TOKEN.get(row.declared_token, row.declared_token)
                legacy_allowed = ks.has_token(auth, legacy_tok)
            elif row.auth_kind == "ws":
                legacy_allowed = ks.has_permission(auth, "GET", row.path)
            else:
                legacy_allowed = ks.has_permission(auth, row.method, concrete_path)

            checked_cells += 1

            if live_allowed != legacy_allowed:
                cell = (role, row.method, row.path)
                if cell in expected_m14t:
                    observed_m14t[cell] = (live_allowed, legacy_allowed)
                elif (
                    role == "mcp_readonly"
                    and live_allowed
                    and not legacy_allowed
                    and row.proposed_token in MCP_READONLY_TWIN_TOKENS
                ):
                    continue
                else:
                    unexpected_deltas[cell] = (live_allowed, legacy_allowed)

    assert checked_cells >= 3000, f"Non-vacuity floor: expected >= 3000 cells, got {checked_cells}"
    assert observed_m14t == expected_m14t
    assert unexpected_deltas == {}


class TestRoleKeyStoreMechanics:
    def test_from_settings_loads_both_permission_map_and_roles(self) -> None:
        s = Settings.from_dict(
            {
                "auth": {
                    "api_keys": [
                        {
                            "key": "SECRET-KEY-VALUE",
                            "name": "Caregiver",
                            "permissions": ["caregiver"],
                            "roles": ["caregiver"],
                        }
                    ],
                    "permission_map": {"caregiver": ["GET /api/v1/*"]},
                    "roles": {"caregiver": ["rooms:read"]},
                }
            }
        )
        ks = KeyStore.from_settings(s)
        assert ks.has_roles_config is True
        ctx = ks.resolve("SECRET-KEY-VALUE")
        assert ctx.roles == ["caregiver"]
        assert ks.has_role_token(ctx, "rooms:read") is True
        assert ks.has_role_token(ctx, "rooms:write") is False

    def test_wildcard_role_grants_all_tokens(self) -> None:
        ks = KeyStore(roles={"admin": ["*"]})
        ctx = AuthContext(key="K", name="Admin", roles=["admin"])
        assert ks.has_role_token(ctx, "anything:delete") is True


class TestInverseShadowObservability:
    def test_inverse_shadow_legacy_would_allow_and_deny_increment_metric_without_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        raw_secret = "SUPER-SECRET-API-KEY-12345"
        ks = KeyStore(
            api_keys=[
                {
                    "key": raw_secret,
                    "name": "Caregiver",
                    "permissions": ["caregiver"],
                    "roles": ["caregiver"],
                }
            ],
            permission_map={
                "caregiver": ["GET /api/v1/only-glob"],
            },
            roles={
                "caregiver": ["only_role:write"],
            },
        )
        monkeypatch.setattr(auth_module, "_default_keystore", ks)

        logged: list[tuple[str, dict[str, Any]]] = []

        class _StubLogger:
            def warning(self, event: str, **kwargs: Any) -> None:
                logged.append((event, kwargs))

            def info(self, event: str, **kwargs: Any) -> None:
                pass

        monkeypatch.setattr(auth_module, "logger", _StubLogger())

        app = FastAPI()

        @app.get("/api/v1/only-glob")
        async def only_glob(
            _a: AuthContext = Depends(require_permission("only_glob:read")),
        ) -> dict[str, bool]:
            return {"ok": True}

        @app.put("/api/v1/only-role")
        async def only_role(
            _a: AuthContext = Depends(require_permission("only_role:write")),
        ) -> dict[str, bool]:
            return {"ok": True}

        legacy_allow_counter = cc_auth_shadow_mismatch_total.labels(
            token="only_glob:read", role="caregiver", decision="legacy_would_allow"
        )
        legacy_deny_counter = cc_auth_shadow_mismatch_total.labels(
            token="only_role:write", role="caregiver", decision="legacy_would_deny"
        )
        allow_before = legacy_allow_counter._value.get()
        deny_before = legacy_deny_counter._value.get()

        client = TestClient(app, raise_server_exceptions=False)
        headers = {"X-API-Key": raw_secret}

        # Live D4 DENY, legacy glob ALLOW -> request fails (!=200), records legacy_would_allow.
        resp1 = client.get("/api/v1/only-glob", headers=headers)
        assert resp1.status_code != 200
        assert legacy_allow_counter._value.get() == allow_before + 1

        # Live D4 ALLOW, legacy glob DENY -> request succeeds (200), records legacy_would_deny.
        resp2 = client.put("/api/v1/only-role", headers=headers)
        assert resp2.status_code == 200
        assert legacy_deny_counter._value.get() == deny_before + 1

        assert len(logged) == 2
        for event, kwargs in logged:
            assert event == "auth_shadow_mismatch"
            assert kwargs["role"] == "caregiver"
            assert raw_secret not in repr(kwargs), "API key must never appear in shadow logs"

    def test_require_token_and_ws_inverse_shadow_record_mismatches(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ks = KeyStore(
            api_keys=[
                {
                    "key": "KEY-1",
                    "name": "Reviewer",
                    "permissions": ["reviewer"],
                    "roles": ["reviewer"],
                }
            ],
            permission_map={"reviewer": ["visitors.review"]},
            roles={"reviewer": []},
        )
        monkeypatch.setattr(auth_module, "_default_keystore", ks)

        app = FastAPI()

        @app.get("/api/v1/visitors/clusters")
        async def clusters(
            _a: AuthContext = Depends(require_token("visitors:review")),
        ) -> dict[str, bool]:
            return {"ok": True}

        tok_counter = cc_auth_shadow_mismatch_total.labels(
            token="visitors:review", role="reviewer", decision="legacy_would_allow"
        )
        before_tok = tok_counter._value.get()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/visitors/clusters", headers={"X-API-Key": "KEY-1"})
        assert resp.status_code != 200
        assert tok_counter._value.get() == before_tok + 1

        ws_counter = cc_auth_shadow_mismatch_total.labels(
            token="cts.live:read", role="reviewer", decision="legacy_would_deny"
        )
        before_ws = ws_counter._value.get()
        auth = ks.resolve("KEY-1")
        evaluate_ws_inverse_shadow(auth, "/ws/cts", "cts.live:read", live_allowed=True, keystore=ks)
        assert ws_counter._value.get() == before_ws + 1

    def test_inverse_shadow_is_noop_when_keystore_has_no_permission_map(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ks = KeyStore(
            api_keys=[{"key": "K", "name": "D4Only", "roles": ["admin"]}],
            roles={"admin": ["*"]},
        )
        monkeypatch.setattr(auth_module, "_default_keystore", ks)

        logged: list[str] = []

        class _StubLogger:
            def warning(self, event: str, **_kwargs: Any) -> None:
                logged.append(event)

        monkeypatch.setattr(auth_module, "logger", _StubLogger())

        evaluate_ws_inverse_shadow(
            ks.resolve("K"), "/ws/cts", "cts.live:read", live_allowed=True, keystore=ks
        )
        assert logged == []
