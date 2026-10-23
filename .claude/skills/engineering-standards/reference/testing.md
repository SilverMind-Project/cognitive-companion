# Testing standards

Read before writing or changing tests. Part of the `engineering-standards` skill; the rules summary is in `../SKILL.md`.

## Testing standards

### Test location and naming

```
backend/tests/<mirror_path>/test_<module>.py
```

- Test files mirror the source tree exactly.
- One test file per source module.
- Test function names: `test_<what>_<condition>_<expected>`. Examples:
  - `test_execute_with_valid_config_returns_success`
  - `test_analyze_when_service_disabled_returns_none`
  - `test_matches_with_cooloff_active_returns_empty_list`

### Test structure (Arrange-Act-Assert)

```python
async def test_execute_with_person_detected_returns_identification():
    # Arrange
    handler = SceneAnalysisHandler()
    step = _make_step({"min_confidence": 0.7})
    services = _make_services(scene_analysis_client=_mock_client())
    trigger = _make_trigger(media_paths=[_MINIO_URL])

    # Act
    result = await handler.execute(step, _FakeExecution(), {}, trigger, services)

    # Assert
    assert result.success is True
    assert result.data.get("detections") == []
```

Keep blank lines between the three blocks.

### Required test cases

Every new public class/function must have tests covering:

1. **Success path**: normal inputs, expected output.
2. **Missing service path**: what happens when an optional service is `None`.
3. **Edge case**: empty input, boundary value, unusual config.

Step handlers, channels, and filters each need all three.

### Fixtures

- Use the conftest fixtures (`db_session`, `db_factory`, `db_engine`). Do not create your own database setups.
- `db_engine` is the session-scoped PostgreSQL/TimescaleDB engine, `db_session` is the per-test SQLAlchemy session, and `db_factory` creates independent sessions that callers must close. The autouse `_truncate_tables` fixture cleans database state after tests that request `db_session` or `db_factory`.
- Test timestamps must be timezone-aware UTC, for example `datetime(2026, 6, 12, tzinfo=UTC)` or `datetime.now(UTC)`. Naive datetimes can compare differently from PostgreSQL `timestamptz` values and create false failures.
- Use `Settings.from_dict({...})` instead of touching config files.
- Use `@dataclass class _FakeStep` instead of constructing `PipelineStep` (SQLAlchemy instrumentation breaks on `__new__`).
- Use `RulesEngine(tz_name="UTC")` to align with testcontainer UTC values.
- Patch HTTP at `unittest.mock.patch("backend.integrations.<module>.httpx.AsyncClient")`.

### Envelope and authorization tests

Browser-visible envelope changes require an MCP/BFF parity test whenever an MCP tool exposes the same concept. Use the existing patterns in:

- `backend/tests/integrations/test_mcp_bff_parity.py` for person-location and heatmap reads.
- `backend/tests/integrations/test_gait_mcp_bff_parity.py` for a domain-specific envelope.
- `backend/tests/routers/test_signals_feed.py` for direct router/service/MCP parity.
- `backend/tests/mcp/test_signal_ack_parity.py` for a mutation.

Every new or changed endpoint also needs an authorization coverage check against `config/auth.yaml`: verify the permission token exists under `permission_map`, verify the intended role includes that token or concrete route pattern, and add a focused route test proving unauthorized access is rejected.

Route-auth coverage is enforced by `backend/tests/routers/test_route_auth_coverage.py`: every route carries `require_permission`/`require_token` (or is in the justified allowlist), every named permission token exists in `config/auth.yaml`, and every route is reachable by at least one configured role. The token-name contract is also checked at startup by `assert_declared_tokens_known()` in the lifespan, so a typo'd token fails the boot rather than lying at the call site. API keys travel in the `X-API-Key` header everywhere except the device surface (`get_auth_context_device`, opted into per call site via `require_permission(..., resolver=...)`); never add a query-param or body key path to a browser-facing endpoint. Accepted risk (recorded 2026-07-15): the admin SPA stores its key in `localStorage`; revisit only as a product decision.

Follow the complete recipe in `/home/sriram/code/nanai/cognitive-companion/.claude/skills/bff-api-design/SKILL.md`; do not duplicate router and MCP business logic in tests.

### What not to do in tests

- Never mock the database. Use testcontainer fixtures.
- Never mutate class-level state with `type(obj).prop = ...`. Use a local subclass.
- Never call external services (no real HTTP, no real MinIO, no real Redis).

### Test quality signals

- A test that doesn't assert anything is broken.
- A test with more mocks than lines of arrange code is testing implementation, not behavior.
- A test that depends on execution order is fragile. Every test sets up its own state.

### A gate that enumerates a collection needs a non-vacuity canary

Any test shaped "no member of this collection violates X" passes trivially when
the collection is empty, and nothing about that failure is visible: the suite
stays green while the gate certifies nothing. Whenever a gate derives its
subjects by enumerating something it does not itself construct (routes on the
app, plugins from a registry, files on disk, rows from a fixture), pin the
enumeration separately:

- assert a **floor** on the size, set far below the real count, so it catches a
  traversal that broke outright rather than needing a bump on every addition;
- assert the collection **spans** its sources (routes from several routers, not
  just the first);
- or cross-check the enumeration against a **static list** the test does not
  derive the same way. `tests/docs/test_doc_registry_parity.py` is the reference:
  it compares each plugin registry bidirectionally against the vocabulary lists
  in `CLAUDE.md`/`AGENTS.md`, so an empty registry fails loudly instead of
  silently satisfying every per-plugin check.

This is not hypothetical. FastAPI 0.139 made `include_router` lazy (`app.routes`
holds opaque `_IncludedRouter` wrappers, expanded at match time), and the
long-standing `[r for r in app.routes if isinstance(r, APIRoute)]` idiom silently
went from 322 routes to 1. The route-auth coverage gate kept passing while
checking a single endpoint, and a later "stale allowlist" cleanup deleted four
security justifications and two assertions that only looked obsolete because the
gate had gone blind. Enumerate through `iter_route_contexts` (see
`backend/tests/routers/_route_inventory.py`, with the canary in
`test_route_inventory.py`), and treat a shrinking gate population as a defect,
never as a cleanup opportunity.

### Injectable clocks for time-based logic

Any component that computes monotonic deadlines, token refills, cooldowns, or
time windows must accept a `time_fn` dependency. Default it to
`time.monotonic`, `datetime.now`, or another production clock appropriate to the
domain. Tests advance a fake clock and must not sleep to exercise time-based
behavior.

`PerCameraRateLimiter` and `CooldownTracker` in
`backend.services.aggregation` are the reference implementations.
