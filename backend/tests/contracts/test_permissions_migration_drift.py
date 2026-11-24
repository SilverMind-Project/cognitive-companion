"""Drift and validity gate for ``docs/api/permissions.md`` and ``config/auth.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.core.auth import ALLOWED_ACTIONS, is_valid_d4_token
from backend.scripts.export_route_permissions import (
    AUTH_YAML_PATH,
    DEFAULT_OUTPUT_PATH,
    collect_route_inventory,
    load_keystore,
    render_permissions_markdown,
)


def test_permissions_doc_is_current() -> None:
    """Regenerate ``docs/api/permissions.md`` in memory and assert zero drift."""
    ks = load_keystore()
    rows = collect_route_inventory()
    expected = render_permissions_markdown(rows, ks)

    assert DEFAULT_OUTPUT_PATH.exists(), f"Missing {DEFAULT_OUTPUT_PATH}"
    actual = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/api/permissions.md is out of date. "
        "Re-run: uv run --project backend python backend/scripts/export_route_permissions.py"
    )


def test_route_inventory_is_non_vacuous_and_every_declared_token_is_d4_valid() -> None:
    """Canary: inventory covers all live routes and every declared token matches D4."""
    rows = collect_route_inventory()
    http_rows = [r for r in rows if r.auth_kind == "http"]
    ws_rows = [r for r in rows if r.auth_kind == "ws"]

    assert len(http_rows) >= 300, f"Expected >= 300 guarded HTTP routes, got {len(http_rows)}"
    assert {r.path for r in ws_rows} == {"/ws/audio", "/ws/cts", "/ws/pipeline"}

    for row in rows:
        assert is_valid_d4_token(row.declared_token), (
            f"{row.method} {row.path}: invalid D4 token {row.declared_token!r}"
        )


def test_d4_token_validator_rejects_legacy_formats_and_unknown_actions() -> None:
    """Canary: D4 grammar rejects role names, dotted names, METHOD /path, and unknown actions."""
    assert is_valid_d4_token("cts.signals:acknowledge")
    assert is_valid_d4_token("rooms:read")
    assert not is_valid_d4_token("admin")
    assert not is_valid_d4_token("cts.cameras.read")
    assert not is_valid_d4_token("GET /api/v1/rooms")
    assert not is_valid_d4_token("wearables:manage")
    assert not is_valid_d4_token("persons:heights_sync")
    assert "manage" not in ALLOWED_ACTIONS


def test_auth_yaml_has_no_legacy_permission_map_and_roles_are_valid() -> None:
    """``config/auth.yaml`` uses only the D4 ``roles:`` shape (no ``permission_map`` or globs)."""
    data = yaml.safe_load(Path(AUTH_YAML_PATH).read_text(encoding="utf-8"))
    assert "permission_map" not in data, "Legacy permission_map must stay deleted"

    actual_roles = data.get("roles", {})
    assert actual_roles, "config/auth.yaml must define roles:"

    for role_name, tokens in actual_roles.items():
        for token in tokens:
            if token == "*":
                continue
            assert is_valid_d4_token(token), (
                f"Role {role_name!r} in config/auth.yaml carries non-D4 token {token!r}"
            )

    for entry in data.get("api_keys", []) + data.get("device_keys", []):
        assert "permissions" not in entry, (
            f"Key {entry.get('name')!r} still carries legacy permissions: field"
        )
        entry_roles = entry.get("roles", [])
        assert entry_roles, f"Key {entry.get('name')!r} is missing roles: list"
        for role_name in entry_roles:
            assert role_name in actual_roles, (
                f"Key {entry.get('name')!r} references undefined role {role_name!r}"
            )
