# API design and security

Read before adding or changing a route. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Security

### Secrets and config

- Secrets live in env vars, never in YAML. Use `${ENV_VAR}` interpolation in config files.
- Validate secrets load at startup. Missing required env vars should fail fast.
- Never log secrets, tokens, or API keys. Mask them in log output.

### Authentication and authorization

- Every new endpoint must have an `auth.yaml` permission entry.
- Use `require_permission(...)` on every route. New routes name a `<resource>:<action>` token (program decision D4, for example `rooms:read`); the legacy `METHOD /path`, dotted, and role-name styles migrate in EG-M14.
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
