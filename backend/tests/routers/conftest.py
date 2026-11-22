"""Shared fixtures for router tests."""

from __future__ import annotations

import pytest

from backend.core import auth as auth_module
from backend.core.auth import KeyStore

# The CTS presence routes require cts.presence.view. Modules that build a bare
# app around those routers opt in with the ``cts_presence_keystore`` fixture
# (via pytest.mark.usefixtures) and send the CTS_PRESENCE_AUTH header.
CTS_PRESENCE_AUTH = {"X-API-Key": "TESTKEY"}


@pytest.fixture
def cts_presence_keystore(monkeypatch: pytest.MonkeyPatch) -> KeyStore:
    """Install a keystore granting the CTS presence surface to ``TESTKEY``."""
    store = KeyStore(
        api_keys=[{"key": "TESTKEY", "name": "test", "roles": ["caregiver"]}],
        roles={"caregiver": ["cts.presence:read", "cts.presence.config:write"]},
    )
    monkeypatch.setattr(auth_module, "_default_keystore", store)
    return store
