"""Export the composed FastAPI route-permission matrix and EG-M14 migration table.

Usage::

    uv run --project backend python backend/scripts/export_route_permissions.py
    uv run --project backend python backend/scripts/export_route_permissions.py --check
    uv run --project backend python backend/scripts/export_route_permissions.py --emit-roles-yaml

Walks ``backend.main.app`` through FastAPI's ``iter_route_contexts`` (the same
traversal used by OpenAPI generation and ``test_route_auth_coverage.py``),
evaluates today's effective reachability for every configured role in
``config/auth.yaml``, maps each route to its proposed D4 token via
``backend.core.permission_migration``, and renders ``docs/api/permissions-migration.md``.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi.routing import APIRoute, iter_route_contexts
from starlette.routing import WebSocketRoute

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.auth import AuthContext, KeyStore  # noqa: E402
from backend.core.permission_migration import (  # noqa: E402
    M14T_CONSOLIDATION_DELTAS,
    M14T_RECOMMENDED_REVIEW_ITEMS,
    ROLE_TO_LEGACY_PERMISSIONS,
    WS_ROUTE_TOKENS,
    resolve_proposed_token,
)

AUTH_YAML_PATH = REPO_ROOT / "config" / "auth.yaml"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "api" / "permissions-migration.md"

_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class RoutePermissionRow:
    method: str
    path: str
    declared_token: str
    auth_kind: str
    proposed_token: str
    reaching_roles: tuple[str, ...]


def _concrete_path(route_template: str) -> str:
    return _PATH_PARAM_RE.sub("sample", route_template)


def _auth_checkers(route: Any) -> list[Any]:
    found: list[Any] = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        if getattr(dep.call, "__cc_auth_checker__", False):
            found.append(dep.call)
        stack.extend(dep.dependencies)
    return found


def _primary_method(methods: set[str] | None) -> str:
    return sorted((methods or set()) - {"HEAD", "OPTIONS"})[0]


def _load_legacy_keystore(auth_yaml: Path = AUTH_YAML_PATH) -> KeyStore:
    data = yaml.safe_load(auth_yaml.read_text(encoding="utf-8")) or {}
    return KeyStore(
        api_keys=data.get("api_keys", []),
        device_keys=data.get("device_keys", []),
        permission_map=data.get("permission_map", {}),
    )


def _legacy_reaches(
    ks: KeyStore,
    role_name: str,
    method: str,
    path: str,
    auth_kind: str,
    declared_token: str,
) -> bool:
    legacy_perms = list(ROLE_TO_LEGACY_PERMISSIONS[role_name])
    auth = AuthContext(key="inventory", name=role_name, permissions=legacy_perms, roles=[role_name])
    if auth_kind == "token":
        return ks.has_token(auth, declared_token)
    return ks.has_permission(auth, method, _concrete_path(path))


def collect_route_inventory(auth_yaml: Path = AUTH_YAML_PATH) -> list[RoutePermissionRow]:
    """Walk the composed app and compute live role reachability for every guarded route."""
    import backend.main

    ks = _load_legacy_keystore(auth_yaml)
    role_order = list(ROLE_TO_LEGACY_PERMISSIONS)
    rows: list[RoutePermissionRow] = []

    for ctx in iter_route_contexts(backend.main.app.routes):
        orig = ctx.original_route
        if isinstance(orig, APIRoute):
            checkers = _auth_checkers(ctx)
            if not checkers:
                continue
            checker = checkers[0]
            auth_kind = str(getattr(checker, "__cc_auth_kind__", "permission"))
            declared_tokens = tuple(getattr(checker, "__cc_auth_tokens__", ()))
            declared = declared_tokens[0] if declared_tokens else ""
            method = _primary_method(ctx.methods)
            proposed = resolve_proposed_token(method, ctx.path, declared)
            reaching = tuple(
                role
                for role in role_order
                if _legacy_reaches(ks, role, method, ctx.path, auth_kind, declared)
            )
            rows.append(
                RoutePermissionRow(
                    method=method,
                    path=ctx.path,
                    declared_token=declared,
                    auth_kind=auth_kind,
                    proposed_token=proposed,
                    reaching_roles=reaching,
                )
            )
        elif isinstance(orig, WebSocketRoute) and orig.path in WS_ROUTE_TOKENS:
            proposed = WS_ROUTE_TOKENS[orig.path]
            reaching = tuple(
                role
                for role in role_order
                if _legacy_reaches(ks, role, "GET", orig.path, "ws", proposed)
            )
            rows.append(
                RoutePermissionRow(
                    method="WS",
                    path=orig.path,
                    declared_token=f"GET {orig.path}",
                    auth_kind="ws",
                    proposed_token=proposed,
                    reaching_roles=reaching,
                )
            )

    rows.sort(key=lambda r: (r.proposed_token, r.path, r.method))
    return rows


def derive_roles_map(rows: list[RoutePermissionRow]) -> dict[str, list[str]]:
    """Derive clean ``roles:`` token sets that reproduce today's access matrix.

    ``admin`` and ``operator`` keep ``["*"]``. Every other role receives a token
    iff every route mapped to that token reaches the role today, adjusted by
    explicitly declared ``M14T_CONSOLIDATION_DELTAS``. MCP-only tokens
    (``mcp.tools:read``, ``rules:import``) are also preserved on their MCP roles.
    """
    token_routes: dict[str, list[RoutePermissionRow]] = defaultdict(list)
    for row in rows:
        token_routes[row.proposed_token].append(row)

    delta_lookup = {(d.role, d.method, d.path): d.proposed for d in M14T_CONSOLIDATION_DELTAS}

    roles_map: dict[str, list[str]] = {
        "admin": ["*"],
        "operator": ["*"],
    }

    for role in ROLE_TO_LEGACY_PERMISSIONS:
        if role in ("admin", "operator"):
            continue
        tokens: set[str] = set()
        for token, rlist in token_routes.items():
            # Apply declared M14-T consolidation outcomes when deciding token grant.
            effective = [
                delta_lookup.get((role, r.method, r.path), role in r.reaching_roles) for r in rlist
            ]
            if all(effective):
                tokens.add(token)
            elif any(effective):
                missing = [
                    f"{r.method} {r.path}" for r, ok in zip(rlist, effective, strict=True) if not ok
                ]
                present = [
                    f"{r.method} {r.path}" for r, ok in zip(rlist, effective, strict=True) if ok
                ]
                raise RuntimeError(
                    f"Unresolved split reachability for role={role!r} token={token!r}: "
                    f"allowed={present}, denied={missing}. Split the token or add an M14-T delta."
                )

        # Preserve MCP endpoint/tool grants that do not live on FastAPI APIRoutes.
        if role == "mcp_readonly":
            tokens.add("mcp.tools:read")
        if role == "mcp_rules_import":
            tokens.add("rules:import")

        roles_map[role] = sorted(tokens)

    return roles_map


def render_migration_markdown(
    rows: list[RoutePermissionRow],
    roles_map: dict[str, list[str]],
) -> str:
    """Render deterministic markdown for ``docs/api/permissions-migration.md``."""
    non_super_roles = [r for r in ROLE_TO_LEGACY_PERMISSIONS if r not in ("admin", "operator")]
    http_rows = [r for r in rows if r.auth_kind != "ws"]
    ws_rows = [r for r in rows if r.auth_kind == "ws"]
    distinct_proposed = sorted({r.proposed_token for r in rows})
    distinct_declared = sorted({r.declared_token for r in http_rows})

    lines: list[str] = [
        "# Permission Token Migration Matrix (EG-M14)",
        "",
        "Generated by `backend/scripts/export_route_permissions.py` from the composed FastAPI",
        "application (`backend.main.app`) and `config/auth.yaml`. Do not hand-edit; re-run the",
        "exporter and commit the diff. Verified by `backend/tests/contracts/test_permissions_migration_drift.py`.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Guarded HTTP routes | {len(http_rows)} |",
        f"| Authenticated WebSocket routes | {len(ws_rows)} |",
        f"| Distinct legacy declared tokens | {len(distinct_declared)} |",
        f"| Distinct proposed D4 tokens | {len(distinct_proposed)} |",
        f"| Configured roles (`roles:`) | {len(roles_map)} |",
        f"| Unavoidable consolidation deltas (M14-T Table A) | {len(M14T_CONSOLIDATION_DELTAS)} |",
        f"| Zero-delta review items (M14-T Table B) | {len(M14T_RECOMMENDED_REVIEW_ITEMS)} |",
        "",
        "## M14-T Owner-Approval Table",
        "",
        "### Table A: Unavoidable token-consolidation deltas",
        "",
        "Every cell where grouping sibling routes under one D4 token changes effective access",
        "relative to today's fnmatch globs. Nothing changes live during PR 1 or PR 2 (shadow only);",
        "owner approval here gates PR 3 enforcement.",
        "",
        "| Role | Route | Proposed token | Today | Proposed | Reason | Recommendation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for delta in M14T_CONSOLIDATION_DELTAS:
        today_s = "ALLOW" if delta.today else "DENY"
        prop_s = "ALLOW" if delta.proposed else "DENY"
        lines.append(
            f"| `{delta.role}` | `{delta.method} {delta.path}` | `{delta.token}` "
            f"| {today_s} | {prop_s} | {delta.reason} | {delta.recommendation} |"
        )

    lines.extend(
        [
            "",
            "### Table B: Recommended tightening and inert-grant review (zero delta in shadow)",
            "",
            "Proposed `roles:` reproduces today's exact reach for every item below so shadow",
            "evaluation stays quiet on live traffic. Review each item before PR 3 to decide whether",
            "to tighten coarse-glob leaks or activate previously inert grants.",
            "",
            "| Roles | Tokens | Today (and shadow) | Recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for role_desc, tok_desc, today_desc, rec in M14T_RECOMMENDED_REVIEW_ITEMS:
        lines.append(f"| {role_desc} | `{tok_desc}` | {today_desc} | {rec} |")

    lines.extend(
        [
            "",
            "## Proposed Role Token Sets (`config/auth.yaml` `roles:`)",
            "",
            "| Role | Legacy `permission_map` keys | Token count | Tokens |",
            "| --- | --- | --- | --- |",
        ]
    )
    for role, tokens in roles_map.items():
        legacy = ", ".join(f"`{k}`" for k in ROLE_TO_LEGACY_PERMISSIONS[role])
        tok_list = ", ".join(f"`{t}`" for t in tokens)
        lines.append(f"| `{role}` | {legacy} | {len(tokens)} | {tok_list} |")

    lines.extend(
        [
            "",
            "## Full Route Inventory and Live Access Matrix",
            "",
            "Roles `admin` and `operator` hold `*` and reach every route below; the table shows",
            "reachability across the remaining configured roles today.",
            "",
            "| Proposed D4 token | Method | Path | Declared today | Kind | "
            + " | ".join(f"`{r}`" for r in non_super_roles)
            + " |",
            "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in non_super_roles) + " |",
        ]
    )
    for row in rows:
        cells = " | ".join("Y" if r in row.reaching_roles else "." for r in non_super_roles)
        lines.append(
            f"| `{row.proposed_token}` | `{row.method}` | `{row.path}` "
            f"| `{row.declared_token}` | `{row.auth_kind}` | {cells} |"
        )

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination markdown path (default: docs/api/permissions-migration.md).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the generated markdown differs from --output.",
    )
    parser.add_argument(
        "--emit-roles-yaml",
        action="store_true",
        help="Print the derived YAML roles: block to stdout and exit.",
    )
    args = parser.parse_args(argv)

    rows = collect_route_inventory()
    roles_map = derive_roles_map(rows)

    if args.emit_roles_yaml:
        sys.stdout.write(yaml.safe_dump({"roles": roles_map}, sort_keys=False))
        return 0

    rendered = render_migration_markdown(rows, roles_map)
    if args.check:
        if not args.output.exists():
            sys.stderr.write(f"Missing generated permissions doc: {args.output}\n")
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing != rendered:
            sys.stderr.write(
                f"Permissions migration doc drift detected in {args.output}. "
                "Re-run backend/scripts/export_route_permissions.py.\n"
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
