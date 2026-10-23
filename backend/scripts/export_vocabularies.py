#!/usr/bin/env python3
"""Export backend-canonical controlled vocabularies to a generated frontend artifact.

The backend is the single source of truth for step types, filter types, channel types, CTS
signal kinds (`ALL_SIGNAL_KINDS`, with the CTS wire subset `WIRE_SIGNAL_KINDS`), and MCP tools with the permission token each requires.
The public documentation site reads `mcp_tools` from this file to check its tool counts. This script writes `frontend/src/generated/vocabularies.json`
for frontend code paths that need synchronous constants (palette fallbacks, select options,
tests) and cannot await a network call. Output is deterministic (sorted keys, sorted lists,
`indent=2`, trailing newline) so `make vocabularies` followed by `git diff --exit-code` is a
clean CI drift gate. Run via ``uv run --project backend python backend/scripts/export_vocabularies.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "frontend" / "src" / "generated" / "vocabularies.json"

# Allow running as `python backend/scripts/export_vocabularies.py` (adds the script's own
# directory to sys.path, not the repo root) as well as `-m` / pytest-style invocation.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_vocabularies() -> dict:
    from backend.channels import ChannelRegistry
    from backend.filters import FilterRegistry
    from backend.mcp.server import _tool_handlers, tool_token
    from backend.services.cts.signal_config import ALL_SIGNAL_KINDS, WIRE_SIGNAL_KINDS
    from backend.steps import StepRegistry

    StepRegistry.discover()
    FilterRegistry.discover()
    ChannelRegistry.discover()

    step_types = [
        {
            "type_name": m.type_name,
            "display_name": m.display_name,
            "icon": m.icon,
            "category": m.category,
            "output_ports": list(m.output_ports),
            "gate_safe": m.gate_safe,
        }
        for m in sorted(StepRegistry.all_metadata(), key=lambda m: m.type_name)
    ]

    return {
        "step_types": step_types,
        "filter_types": sorted(FilterRegistry.all_names()),
        "channel_types": sorted(ChannelRegistry.all_names()),
        "signal_kinds": sorted(ALL_SIGNAL_KINDS),
        "wire_signal_kinds": sorted(WIRE_SIGNAL_KINDS),
        "mcp_tools": sorted(_tool_handlers),
        "mcp_tool_tokens": {name: tool_token(name) for name in sorted(_tool_handlers)},
    }


def main() -> None:
    vocabularies = build_vocabularies()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(vocabularies, indent=2, sort_keys=True) + "\n"
    OUTPUT_PATH.write_text(text)
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
