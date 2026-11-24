# API design and security

Read before adding or changing a route. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Security

### Secrets and config

- Secrets live in env vars, never in YAML. Use `${ENV_VAR}` interpolation in config files.
- Validate secrets load at startup. Missing required env vars should fail fast.
- Never log secrets, tokens, or API keys. Mask them in log output.

### Authentication and authorization

- Every guarded route, WebSocket endpoint, and MCP tool declares exactly one D4 `<resource>:<action>` token (actions from the closed `ALLOWED_ACTIONS` set in `backend/core/auth.py`). Roles are token sets defined exclusively under `roles:` in `config/auth.yaml`, and authorization checks pure token membership.
- Use `require_permission("<resource>:<action>")` on every HTTP route. List every token on at least one role in `config/auth.yaml` (admin-only tokens appear explicitly under `admin:` alongside `"*"`) and regenerate `docs/api/permissions.md` via `backend/scripts/export_route_permissions.py`.
- Every WebSocket route authenticates through `backend.core.auth.authenticate_websocket(websocket, token, channel=...)` and lists its token in `WS_ROUTE_TOKENS`. A browser cannot set headers on a WebSocket, so it offers the key as its `Sec-WebSocket-Protocol`; the route must accept with `subprotocol=ws_auth.subprotocol`, or the browser drops the connection (close 1006). Never put a key in a WebSocket URL.
- Keys come from the `X-API-Key` header. Only device endpoints (`get_auth_context_device`, opted into per route) also accept a `?api_key` query parameter or a body `device_key`; never add those key paths to a browser-facing route (`testing.md`, "Envelope and authorization tests").

### Input validation

- All input passes through Pydantic schemas (`extra="forbid"`).
- Validate string lengths and numeric ranges explicitly in schemas.
- Template rendering (Jinja2) must not execute arbitrary Python. The `render_template()` helper uses sandboxed evaluation.

## API design

### Router conventions

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.schemas.resource import ResourceCreate, ResourceOut, ResourceUpdate

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceOut])
def list_resources(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("resources:read")),
):
    return db.query(Resource).order_by(Resource.name).all()
```

- Use `response_model` on every route.
- Use plural nouns for collection routes (`/resources`), singular with id for item routes (`/resources/{resource_id}`).
- POST returns `status_code=201`.
- Auth is always the last Depends (underscore-prefixed if unused in body).
- Router tags match the resource name.

### Pagination

List endpoints that can grow must support server-side pagination:

```python
@router.get("", response_model=ResourceListOut)
def list_resources(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("resources:read")),
):
    total = db.query(func.count(Resource.id)).scalar()
    items = db.query(Resource).order_by(Resource.name).offset(offset).limit(limit).all()
    return {"items": items, "total": total}
```

The response schema must include `total: int`:
```python
class ResourceListOut(BaseModel):
    items: list[ResourceOut]
    total: int
```
