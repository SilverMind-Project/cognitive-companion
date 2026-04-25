"""Root conftest for the backend test suite.

Fixes a sys.path shadowing issue: pytest adds the rootdir (backend/) to
sys.path, which causes ``backend/mcp/`` to shadow the ``mcp`` PyPI package.
This file runs before any test collection and ensures the workspace root is
on sys.path so that ``import mcp`` resolves to the installed package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Workspace root is one level above this file (backend/../)
_workspace_root = str(Path(__file__).parent.parent)

# Insert workspace root at position 0 so it takes precedence over backend/
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

# Remove bare backend/ entry that pytest adds, which causes backend/mcp/ to
# shadow the mcp PyPI package. The backend package is still importable via
# the workspace root entry added above.
_backend_dir = str(Path(__file__).parent)
while _backend_dir in sys.path:
    sys.path.remove(_backend_dir)
