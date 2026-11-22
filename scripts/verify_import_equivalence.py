#!/usr/bin/env python3
"""Prove that EG-M12 changed only relative-import spelling in cognitive-companion.

For every changed non-test Python file under ``backend/``:
1. Parse HEAD and working-tree ASTs.
2. Walk every statement-list scope in lockstep, resolving each relative ``ImportFrom``
   in HEAD via ``importlib.util.resolve_name`` and asserting the exact multiset of
   imported ``(module, name, asname)`` bindings in that scope is unchanged and that
   no relative imports remain in non-``__init__.py`` files.
3. Strip all ``Import`` / ``ImportFrom`` nodes from both ASTs and assert
   ``ast.dump(..., include_attributes=False)`` is byte-identical.

Exits non-zero on any mismatch or if zero files / zero relative imports were checked.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCOPE_PREFIX = "backend/"
_EXCLUDED_PREFIXES = ("backend/tests/", "backend/scripts/")

ImportBinding = tuple[str, str, str | None]


def _git_stdout(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _package_for_file(repo_rel_path: str) -> str:
    parts = list(Path(repo_rel_path).with_suffix("").parts)
    if parts[-1] == "__init__":
        return ".".join(parts[:-1])
    return ".".join(parts[:-1])


def _resolve_import_from(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:
        return node.module or ""
    dots = "." * node.level
    target = f"{dots}{node.module}" if node.module else dots
    return importlib.util.resolve_name(target, package)


def _extract_scope_imports(
    stmts: list[ast.stmt], package: str, *, allow_relative: bool
) -> tuple[Counter[ImportBinding], int]:
    bindings: Counter[ImportBinding] = Counter()
    relative_count = 0
    for stmt in stmts:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                bindings[("__import__", alias.name, alias.asname)] += 1
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.level > 0:
                if not allow_relative:
                    raise AssertionError(
                        f"unexpected relative import remaining: level={stmt.level} module={stmt.module!r}"
                    )
                relative_count += len(stmt.names)
            mod = _resolve_import_from(stmt, package)
            for alias in stmt.names:
                bindings[(mod, alias.name, alias.asname)] += 1
    return bindings, relative_count


def _stmt_lists(node: ast.AST) -> list[list[ast.stmt]]:
    lists: list[list[ast.stmt]] = []
    for field_name in ("body", "orelse", "finalbody"):
        val = getattr(node, field_name, None)
        if isinstance(val, list) and all(isinstance(x, ast.stmt) for x in val):
            lists.append(val)
    handlers = getattr(node, "handlers", None)
    if isinstance(handlers, list):
        for handler in handlers:
            if isinstance(handler, ast.ExceptHandler):
                lists.append(handler.body)
    cases = getattr(node, "cases", None)
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, ast.match_case):
                lists.append(case.body)
    return lists


def _strip_imports(tree: ast.AST) -> ast.AST:
    cloned = copy.deepcopy(tree)

    class _Stripper(ast.NodeTransformer):
        def visit_Import(self, node: ast.Import) -> None:
            return None

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            return None

    return _Stripper().visit(cloned)


def _compare_scopes(
    old_node: ast.AST,
    new_node: ast.AST,
    package: str,
    rel_path: str,
    *,
    allow_new_relative: bool,
) -> int:
    old_lists = _stmt_lists(old_node)
    new_lists = _stmt_lists(new_node)
    if len(old_lists) != len(new_lists):
        raise AssertionError(
            f"{rel_path}: scope structure mismatch ({len(old_lists)} vs {len(new_lists)})"
        )

    converted = 0
    for old_stmts, new_stmts in zip(old_lists, new_lists, strict=True):
        old_imp, rel_count = _extract_scope_imports(old_stmts, package, allow_relative=True)
        new_imp, _ = _extract_scope_imports(
            new_stmts, package, allow_relative=allow_new_relative
        )
        if old_imp != new_imp:
            removed = old_imp - new_imp
            added = new_imp - old_imp
            raise AssertionError(
                f"{rel_path}: resolved import mismatch\n  removed: {removed}\n  added:   {added}"
            )
        converted += rel_count

        old_non_imp = [s for s in old_stmts if not isinstance(s, (ast.Import, ast.ImportFrom))]
        new_non_imp = [s for s in new_stmts if not isinstance(s, (ast.Import, ast.ImportFrom))]
        if len(old_non_imp) != len(new_non_imp):
            raise AssertionError(
                f"{rel_path}: non-import statement count changed "
                f"({len(old_non_imp)} vs {len(new_non_imp)})"
            )
        for o_stmt, n_stmt in zip(old_non_imp, new_non_imp, strict=True):
            converted += _compare_scopes(
                o_stmt, n_stmt, package, rel_path, allow_new_relative=allow_new_relative
            )
    return converted


def verify_file(rel_path: str) -> int:
    old_src = _git_stdout("show", f"HEAD:{rel_path}")
    new_src = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")

    old_ast = ast.parse(old_src, filename=f"HEAD:{rel_path}")
    new_ast = ast.parse(new_src, filename=rel_path)

    package = _package_for_file(rel_path)
    is_init = Path(rel_path).name == "__init__.py"

    converted = _compare_scopes(
        old_ast, new_ast, package, rel_path, allow_new_relative=is_init
    )

    old_dump = ast.dump(_strip_imports(old_ast), include_attributes=False)
    new_dump = ast.dump(_strip_imports(new_ast), include_attributes=False)
    if old_dump != new_dump:
        raise AssertionError(f"{rel_path}: non-import AST differs after import conversion")

    return converted


def main() -> int:
    changed = [
        line.strip()
        for line in _git_stdout("diff", "--name-only", "HEAD").splitlines()
        if line.strip().endswith(".py")
        and line.strip().startswith(_SCOPE_PREFIX)
        and not any(line.strip().startswith(ex) for ex in _EXCLUDED_PREFIXES)
    ]
    if not changed:
        print("FAIL: no changed Python files found under backend/", file=sys.stderr)
        return 1

    total_converted = 0
    errors: list[str] = []
    for rel_path in changed:
        try:
            total_converted += verify_file(rel_path)
        except Exception as exc:
            errors.append(str(exc))

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    if total_converted == 0:
        print("FAIL: 0 relative imports were converted", file=sys.stderr)
        return 1

    print(
        f"OK: verified {len(changed)} files, {total_converted} relative imports resolved "
        "identically with byte-identical non-import ASTs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
