"""Shared fixtures for router tests."""

from __future__ import annotations

import pytest

from backend.core import auth as auth_module
from backend.core.auth import KeyStore

# the CTS presence routes require cts.presence.view. Modules that build a
# bare app around those routers opt in with:
#
#     pytestmark = pytest.mark.usefixtures("cts_presence_keystore")
#
# and send the CTS_PRESENCE_AUTH header on each request.
CTS_PRESENCE_AUTH = {"X-API-Key": "TESTKEY"}


@pytest.fixture
def cts_presence_keystore(monkeypatch: pytest.MonkeyPatch) -> KeyStore:
    """Install a keystore granting the CTS presence surface to ``TESTKEY``."""
    store = KeyStore(
        api_keys=[{"key": "TESTKEY", "name": "test", "permissions": ["caregiver"]}],
        permission_map={"caregiver": ["cts.presence.view", "* /api/v1/cts/presence*"]},
    )
    monkeypatch.setattr(auth_module, "_default_keystore", store)
    return store
