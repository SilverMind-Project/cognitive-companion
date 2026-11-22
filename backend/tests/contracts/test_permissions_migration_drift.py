"""Drift and validity gate for EG-M14 ``docs/api/permissions-migration.md`` and ``roles:``."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.core.permission_migration import (
    ALLOWED_ACTIONS,
    is_valid_d4_token,
    resolve_proposed_token,
)
from backend.scripts.export_route_permissions import (
    AUTH_YAML_PATH,
    DEFAULT_OUTPUT_PATH,
    collect_route_inventory,
    derive_roles_map,
    render_migration_markdown,
)


def test_permissions_migration_doc_is_current() -> None:
    """Regenerate ``docs/api/permissions-migration.md`` in memory and assert zero drift."""
    rows = collect_route_inventory()
    roles_map = derive_roles_map(rows)
    expected = render_migration_markdown(rows, roles_map)

    assert DEFAULT_OUTPUT_PATH.exists(), f"Missing {DEFAULT_OUTPUT_PATH}"
    actual = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/api/permissions-migration.md is out of date. "
        "Re-run: uv run --project backend python backend/scripts/export_route_permissions.py"
    )


def test_route_inventory_is_non_vacuous_and_every_proposed_token_is_d4_valid() -> None:
    """Canary: inventory covers all live routes and every proposed token matches D4."""
    rows = collect_route_inventory()
    http_rows = [r for r in rows if r.auth_kind != "ws"]
    ws_rows = [r for r in rows if r.auth_kind == "ws"]

    assert len(http_rows) >= 300, f"Expected >= 300 guarded HTTP routes, got {len(http_rows)}"
    assert {r.path for r in ws_rows} == {"/ws/cts", "/ws/pipeline"}

    for row in rows:
        assert is_valid_d4_token(row.proposed_token), (
            f"{row.method} {row.path}: invalid D4 token {row.proposed_token!r}"
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
    assert resolve_proposed_token(
        "POST", "/api/v1/cts/signals/{signal_id}/ack", "cts.signals.view"
    ) == ("cts.signals:acknowledge")


def test_auth_yaml_roles_match_derived_access_matrix_and_are_d4_valid() -> None:
    """``config/auth.yaml`` ``roles:`` stays locked to the derived matrix and D4 grammar."""
    rows = collect_route_inventory()
    expected_roles = derive_roles_map(rows)

    data = yaml.safe_load(Path(AUTH_YAML_PATH).read_text(encoding="utf-8"))
    actual_roles = data.get("roles", {})
    assert actual_roles == expected_roles

    for role_name, tokens in actual_roles.items():
        for token in tokens:
            if token == "*":
                continue
            assert is_valid_d4_token(token), (
                f"Role {role_name!r} in config/auth.yaml carries non-D4 token {token!r}"
            )

    # Every configured API key and device key carries at least one defined role.
    for entry in data.get("api_keys", []) + data.get("device_keys", []):
        entry_roles = entry.get("roles", [])
        assert entry_roles, f"Key {entry.get('name')!r} is missing EG-M14 roles: list"
        for role_name in entry_roles:
            assert role_name in actual_roles, (
                f"Key {entry.get('name')!r} references undefined role {role_name!r}"
            )
