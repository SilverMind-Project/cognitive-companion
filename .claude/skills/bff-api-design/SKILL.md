---
name: bff-api-design
description: How to add a BFF endpoint that is MCP-parity-safe by construction: define the envelope, write the service function once, expose it through both a router and an MCP adapter, add the parity test, the auth.yaml permission, and the import-linter contract.
---

# BFF API Design

This skill covers how to add a new endpoint to the Cognitive Companion BFF in a way that automatically satisfies the MCP/BFF parity guarantee (design rule D6): the same service function powers both the Vue UI router and the MCP tool.

## The invariant

> Any data exposed to the Vue UI through a router must be exposed to MCP tools by reading the **same** service function.

MCP tools may not contain query logic, repository imports, or database access. They call service methods.

## Step-by-step checklist

### 1. Define the response envelope

Create or extend a Pydantic v2 model in `backend/schemas/`. If the data carries quality metadata from CTS, add the four standard fields (see engineering-standards skill section 21):

```python
# backend/schemas/my_resource.py
from pydantic import BaseModel, Field

class MyResourceEnvelope(BaseModel):
    resource_id: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)
    staleness_seconds: int = Field(ge=0)
    source: str
```

### 2. Write the service function once

Add the business logic to an existing service in `backend/services/` or create a new one. The function returns the envelope or raises an `AppError` subclass; it never returns a fabricated value on error.

When the BFF adapts an upstream service, validate the upstream envelope before enrichment. Required list/object/scalar fields must be present with the expected shape. Treat missing fields, wrong JSON types, and upstream 5xx responses as contract failures: log with upstream URL/status and return a typed 502/503. Do not use `.get("required_field", [])` for required data; that converts contract drift into an empty UI and makes incidents invisible.

```python
# backend/services/my_service.py
async def get_my_resource(resource_id: str) -> MyResourceEnvelope:
    row = await self._repo.get(resource_id)
    if row is None:
        raise NotFoundError("MyResource", resource_id)
    return MyResourceEnvelope(
        resource_id=resource_id,
        value=row.value,
        confidence=row.confidence,
        quality=row.quality,
        staleness_seconds=_staleness(row.last_updated_at),
        source=row.source,
    )
```

### 3. Wire the service in the lifespan

Add an attribute to `app.state` in `backend/main.py` (lifespan). Set it to `None` in every branch so the attribute always exists:

```python
# backend/main.py (lifespan)
app.state.my_service = MyService(...)
```

Add a typed dependency in `backend/routers/dependencies.py`:

```python
from backend.services.my_service import MyService

def get_my_service(request: Request) -> MyService:
    svc: MyService | None = request.app.state.my_service
    if svc is None:
        raise HTTPException(status_code=503, detail="my_service unavailable")
    return svc
```

### 4. Add the router endpoint

```python
# backend/routers/my_resource.py
@router.get("/{resource_id}", response_model=MyResourceEnvelope)
async def get_my_resource(
    resource_id: str,
    svc: MyService = Depends(get_my_service),
    _auth: AuthContext = Depends(require_permission("my_resource:read")),
) -> MyResourceEnvelope:
    return await svc.get_my_resource(resource_id)
```

### 5. Add the auth.yaml permission entry

Every new endpoint needs a permission entry in `config/auth.yaml`. No endpoint is discoverable without it.

```yaml
# config/auth.yaml
caregiver:
  - "GET /api/v1/my-resource/*"
```

Verify: `grep "my_resource" config/auth.yaml` must return a match before marking done.

### 6. Add the MCP tool

Add a `@_register` decorated function in `backend/mcp/server.py`. It calls the same service function; it does not import a repository or run a query:

```python
@_register
async def get_my_resource(resource_id: str) -> dict:
    """Get a my-resource envelope by ID."""
    svc: MyService = request.app.state.my_service
    if svc is None:
        return {"error": "service unavailable"}
    env = await svc.get_my_resource(resource_id)
    return env.model_dump(mode="json")
```

Add the tool name to `config/settings.yaml` under `mcp.tools`.

### 7. Add to the import-linter contract

`backend/pyproject.toml` contains `[tool.importlinter]` contract definitions. Ensure `backend.mcp` is not permitted to import from `backend.models` or `backend.services.*.repo`:

```toml
# pyproject.toml (add or verify)
[[tool.importlinter.contracts]]
name = "mcp-no-direct-db"
type = "forbidden"
source_modules = ["backend.mcp"]
forbidden_modules = ["backend.models", "backend.services.my_service._repo"]
```

Run `make import-lint` to verify.

### 8. Add the parity test

Add a test in `backend/tests/mcp/test_parity.py` (or the nearest equivalent) that asserts the MCP tool and the router return the same shape for the same input:

```python
async def test_my_resource_parity(db_session, app_state):
    resource_id = "test-123"
    # Router path
    router_result = await get_my_resource_endpoint(resource_id, svc=app_state.my_service)
    # MCP path
    mcp_result = await mcp_get_my_resource(resource_id)
    assert router_result.resource_id == mcp_result["resource_id"]
    assert router_result.confidence == mcp_result["confidence"]
```

### 9. Update the docs and CLAUDE.md

Add the endpoint to `docs/api/reference.md`. If the surface area is significant, add a feature page.

## Verification commands

```bash
# Import linter
make import-lint

# Parity tests
backend/.venv/bin/pytest backend/tests/mcp/ -v

# Auth coverage: no endpoint without a permission
grep "my_resource" config/auth.yaml
grep "my_resource" backend/routers/my_resource.py
```

## Common mistakes

| Mistake | Correct approach |
|---------|-----------------|
| MCP tool imports `Session` or runs a query | Call the service method; the service owns the query |
| Router and MCP tool each call different service methods | One service method, two callers |
| Missing `auth.yaml` entry | CI catches this; do not merge without it |
| MCP tool returns `{}` on error | Return `{"error": "..."}` with a log; let the caller surface the error |
| Fabricating a default value when data is missing | Raise `NotFoundError` or return documented `None`; never invent data |
| `.get("items", [])` on a required upstream envelope | Validate with Pydantic or explicit type checks; return 502 on contract violation |
