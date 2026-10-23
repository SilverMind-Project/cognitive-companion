---
paths: ["**/backend/**"]
---

# Python environment

- Run Python only through the project venv: `backend/.venv/bin/python`, `uv run --frozen
  --project backend ...`, or a `make` target. Never system Python or `pip install`.
- `backend/uv.lock` changes only when you re-lock on purpose (`uv lock --project backend`);
  the commit hook re-locks the version bump itself. Revert any other `uv.lock` change.
- Format only the files you touched: never `ruff format backend` or `ruff format .`.
