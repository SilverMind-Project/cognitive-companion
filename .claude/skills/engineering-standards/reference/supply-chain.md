# Supply-chain security

Read before changing dependencies, lock files, or toolchain versions. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Supply-chain security

### Toolchain versions (as of 2026-06-01)

| Component | Required minimum | Rationale |
| --- | --- | --- |
| Node.js | 24.16.0 LTS (Krypton), enforced by `frontend/.nvmrc`, `frontend/package.json` engines, and `frontend/Dockerfile` | Node 24 is the latest active LTS; Node 20 is EOL. Keep local, CI, and Docker builds on the same latest LTS patch. |
| Vite | 8.x | Node 24 LTS supported; Rolldown bundler, faster cold starts |
| ECharts | 6.x with vue-echarts 8.x | Tree-shaking API unchanged; vue-echarts 8 requires ECharts 6 |
| Vuetify | 3.12+ (v3 stable branch) | Vuetify 4 is a ground-up rewrite; v3 remains maintained |
| Python | 3.14 | Minimum is set in `requires-python` in `pyproject.toml` |
| redis-py | 8.0 | Minimum floor raised; RESP3 types in 8.x require the `type: ignore[index,assignment]` note in `stream_consumer.py` |
| pillow | 12.0 | Multiple CVEs patched between 10 and 12 |
| pyjwt | 2.13 | RSA/ECDSA bundled; `[cryptography]` extra dropped |

### Lock-file discipline

- `frontend/package-lock.json` is committed and used in CI via `npm ci` (never `npm install`).
- `backend/uv.lock` is committed and used in CI via `uv sync --frozen --extra dev`.
- Neither lock file is edited by hand. Update the lock with `npm install` (frontend) or `uv lock --upgrade` (backend), then commit the change.
- The version bump on commits to `main` (`.githooks/pre-commit`, installed by `make install-hooks`) re-locks offline and stages `backend/uv.lock` with the bumped `pyproject.toml`, so the lock never trails the version. `frontend/openapi.json` pins `info.version` to `"contract"` (`backend/scripts/export_openapi.py`), so a bump never trips the contract drift gate.
- Markdown has no em-dashes, enforced by `scripts/check-no-em-dash.sh` in the pre-commit hook, `make check-md` (in `make check`/`check-all`), and CI.
- When the Node latest LTS patch changes, update `frontend/.nvmrc`, `frontend/package.json` engines, `frontend/Dockerfile`, and `frontend/package-lock.json` together. Verify with `nvm use $(cat frontend/.nvmrc)`, `npm run build`, `npm run test -- --reporter=dot`, and `npm audit --audit-level=high`.

### Dependency scanning

- Run `npm audit --audit-level=high` before every PR; this is in the pre-commit checklist.
- For Python: `uv pip list --outdated --python backend/.venv` shows drift from the lock.
- Recommended CI gate: add `pip-audit` (PyPI) or `osv-scanner` (multi-ecosystem) as a CI step that fails on critical/high CVEs.
- Automated PRs: add a Dependabot config at `.github/dependabot.yml` targeting both `npm` (frontend) and `pip` (backend/pyproject.toml) on a weekly schedule.

### Integrity hygiene

- Prefer `--save-exact` (or `--save-exact` equivalent) for packages directly handling auth, crypto, or serialization to prevent accidental float to a vulnerable patch.
- Never use `npm install <package>` in CI. Use `npm ci` which validates the lockfile hash.
- For the Python side: `uv sync --frozen` aborts if the lock is out of date with `pyproject.toml`, which prevents silent drift.

### Third-party git sources

The `triton-shared` package is sourced directly from a GitHub repo via `[tool.uv.sources]`. This bypasses PyPI release signing. Before updating the pinned commit, verify the commit is on the expected branch and review the diff.
