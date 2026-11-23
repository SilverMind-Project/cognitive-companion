"""The HA WebSocket session against a fake Home Assistant speaking the real protocol.

The older tests mock the subscription itself, so the handshake never ran under test,
and a handshake that never authenticated against a real server went unnoticed. Here
a local server plays Home Assistant: greet with ``auth_required``, accept ``auth``,
answer ``subscribe_events`` with a result, push a ``state_changed`` event, and serve
``/api/states/{entity_id}`` for the initial snapshot.
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn
from fastapi import FastAPI, Request, WebSocket

from backend.integrations.homeassistant import HaStateEvent, _HaWsSession

TOKEN = "test-token"
ENTITY = "binary_sensor.bed_occupancy"


def _fake_ha(*, accept_token: str) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    received: list[dict] = []

    @app.websocket("/api/websocket")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "auth_required", "ha_version": "test"}))
        auth = json.loads(await websocket.receive_text())
        received.append(auth)
        if auth.get("access_token") != accept_token:
            await websocket.send_text(json.dumps({"type": "auth_invalid", "message": "Invalid"}))
            await websocket.close()
            return
        await websocket.send_text(json.dumps({"type": "auth_ok", "ha_version": "test"}))
        sub = json.loads(await websocket.receive_text())
        received.append(sub)
        await websocket.send_text(json.dumps({"id": sub["id"], "type": "result", "success": True}))
        event = {
            "id": sub["id"],
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": ENTITY,
                    "new_state": {"state": "off", "attributes": {}, "last_changed": None},
                },
            },
        }
        await websocket.send_text(json.dumps(event))
        await asyncio.sleep(5)

    @app.get("/api/states/{entity_id}")
    async def state(entity_id: str, request: Request) -> dict:
        return {"entity_id": entity_id, "state": "on", "attributes": {}, "last_changed": None}

    return app, received


@asynccontextmanager
async def _serve(app: FastAPI):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    # Listening before the server starts queues early connections, so the client never
    # has to wait for startup.
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
        sock.close()


@pytest.mark.asyncio
async def test_session_authenticates_snapshots_and_receives_events() -> None:
    app, received = _fake_ha(accept_token=TOKEN)
    events: list[HaStateEvent] = []
    got_both = asyncio.Event()

    async def on_state_changed(event: HaStateEvent) -> None:
        events.append(event)
        if len(events) >= 2:
            got_both.set()

    async with _serve(app) as base_url:
        session = _HaWsSession(base_url, TOKEN, {ENTITY}, on_state_changed)
        await session.start()
        try:
            await asyncio.wait_for(got_both.wait(), timeout=10)
        finally:
            await session.stop()

    assert received[0] == {"type": "auth", "access_token": TOKEN}
    assert received[1]["type"] == "subscribe_events"
    assert sorted(e.state for e in events) == ["off", "on"]  # REST snapshot + live event
    assert {e.entity_id for e in events} == {ENTITY}


@pytest.mark.asyncio
async def test_rejected_token_is_logged_with_its_cause_and_never_dispatches(caplog) -> None:
    app, _received = _fake_ha(accept_token="the-right-token")
    events: list[HaStateEvent] = []

    async def on_state_changed(event: HaStateEvent) -> None:
        events.append(event)

    async with _serve(app) as base_url:
        session = _HaWsSession(base_url, TOKEN, {ENTITY}, on_state_changed)
        with caplog.at_level("WARNING", logger="backend.integrations.homeassistant"):
            await session.start()
            await asyncio.sleep(0.5)
            await session.stop()

    reconnects = [r.getMessage() for r in caplog.records if "ha_ws_reconnect" in r.getMessage()]
    assert reconnects, "a rejected token must surface as a reconnect with its cause"
    assert "auth_invalid" in reconnects[0]
    assert TOKEN not in reconnects[0]
    assert events == []


@pytest.mark.asyncio
async def test_unknown_entity_is_logged_and_stop_is_prompt(caplog) -> None:
    app, _received = _fake_ha(accept_token=TOKEN)

    @app.get("/api/states/light.missing")
    async def missing() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404)

    app.router.routes.insert(0, app.router.routes.pop())  # match before the catch-all
    events: list[HaStateEvent] = []

    async def on_state_changed(event: HaStateEvent) -> None:
        events.append(event)

    async with _serve(app) as base_url:
        session = _HaWsSession(base_url, TOKEN, {"light.missing"}, on_state_changed)
        with caplog.at_level("WARNING", logger="backend.integrations.homeassistant"):
            await session.start()
            await asyncio.sleep(0.5)
            loop = asyncio.get_running_loop()
            started = loop.time()
            await session.stop()
            stopped_in = loop.time() - started

    messages = [r.getMessage() for r in caplog.records]
    assert any("ha_entity_not_found entity_id=light.missing" in m for m in messages)
    assert not any("ha_ws_stop_timeout" in m for m in messages)
    assert stopped_in < 1.0
