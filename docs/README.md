# Cognitive Companion Repository Documentation

This directory holds engineering, API contract, and maintenance documentation needed inside a standalone checkout of `cognitive-companion`.

## Documentation Delineation Standard (Code Repository vs. Skills vs. Public Portal)

Every documentation artifact across the SilverMind repositories belongs in exactly one of three tiers. Never duplicate prose across tiers.

| Tier | Location | Primary Audience | What Belongs Here | What Does Not Belong Here |
| --- | --- | --- | --- | --- |
| **1. Normative Agent and Contributor Rules** | `CLAUDE.md`, `AGENTS.md`, `.claude/skills/`, `.claude/rules/` | AI coding agents and contributors modifying code in this repository | Enforced architectural invariants, layering rules, BFF/MCP parity rules, frontend and chart conventions, CTS admin rules, and test gates (`make docs-check` and `test_doc_registry_parity.py` enforced) | Multi-page user tutorials, product overviews, or historical milestone logs |
| **2. In-Repository Engineering and Contract Docs** | `docs/` (this directory) | Engineers and operators working inside a single repository checkout | 1. **`systems-architecture.md`**: Canonical single-file technical architecture reference for this repository.<br>2. **`api/reference.md`**: In-repository BFF HTTP and MCP endpoint contract reference.<br>3. **`maintenance/`**: Repo-specific database maintenance scripts (`cleanup_legacy_door_zones.sql`). | Drafts or duplicate copies of pages published on `silvermind-project.github.io/docs/`, or pre-implementation design plans whose milestones have already shipped |
| **3. Public Documentation Portal** | `../silvermind-project.github.io/docs/` | Caregivers, care partners, operators, and external developers | Family and privacy pages (`docs/families/`), installation and deployment guides (`docs/guide/`), feature guides (`docs/features/`), hardware guides (`docs/hardware/`), public REST API reference (`docs/api/reference.md`), and cross-repo development guides (`docs/development/`) | Repo-internal Claude hooks, throwaway spike notes, or unshipped feature claims presented as deployed |

## Documents in This Directory

| File | Kind | Purpose |
| --- | --- | --- |
| [systems-architecture.md](systems-architecture.md) | Architecture reference | Single-file technical reference for `cognitive-companion`: runtime stack, backend layering, unified camera aggregation and image rate limiting, rules and graph pipelines, unified execution observability, plugin registries (29 step types, 7 channels, 13 filters), CTS integration and `PersonLocationService` SSOT, and frontend surfaces |
| [api/reference.md](api/reference.md) | API contract reference | Complete BFF HTTP (`/api/v1/*`), WebSocket (`/ws/pipeline`), and MCP (`/mcp`) contract reference, including permissions, envelopes, and error codes |
| [maintenance/cleanup_legacy_door_zones.sql](maintenance/cleanup_legacy_door_zones.sql) | Maintenance script | Idempotent operator SQL cleanup for legacy door-zone records |
