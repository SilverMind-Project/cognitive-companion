# Rule inventory: EG-M08 restructure of the CC skills

Every section of the pre-restructure `engineering-standards` and `front-end` SKILL.md, and
where it now lives. Sections moved verbatim (then fixed in place); SKILL.md restates their
rules as one-liners with a pointer. Delete this file after the restructure is reviewed.

| Skill | Section | Destination |
| --- | --- | --- |
| engineering-standards | ## 1. Naming conventions | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 2. Code organization | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 3. Type safety | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 4. Error handling | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 5. Logging | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 6. Testing standards | `engineering-standards/reference/testing.md` |
| engineering-standards | ## 7. Database patterns | `engineering-standards/reference/database.md` |
| engineering-standards | ## 8. Security | `engineering-standards/reference/api-and-security.md` |
| engineering-standards | ## Consuming a new CTS signal kind | `engineering-standards/reference/pipelines-and-plugins.md` |
| engineering-standards | ## 9. Plugin development | `engineering-standards/reference/pipelines-and-plugins.md` |
| engineering-standards | ## 10. API design | `engineering-standards/reference/api-and-security.md` |
| engineering-standards | ## 11. Time and timezone | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 12. Frontend standards | removed: front-end skill owns these rules; SKILL.md keeps a pointer |
| engineering-standards | ## 13. Python virtual environment | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 14. Pre-commit checklist | `engineering-standards/reference/checklist.md` |
| engineering-standards | ## 15. Common anti-patterns | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 15b. Router service access | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 16. When to abstract | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 20. MCP and BFF single-service-layer rule (D6) | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 21. Unified envelope pattern | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 22. No-silent-fallback lint rule | `engineering-standards/reference/conventions.md` |
| engineering-standards | ## 17. CTS-specific standards | `engineering-standards/reference/cts-integration.md` |
| engineering-standards | ## 18. Frontend composables | `front-end/reference/api-and-state.md` |
| engineering-standards | ## 19. CTS integration design principles | `engineering-standards/reference/cts-integration.md` |
| engineering-standards | ## 23. Supply-chain security | `engineering-standards/reference/supply-chain.md` |
| engineering-standards | ## 24. Guided task and interactive sessions | `engineering-standards/reference/pipelines-and-plugins.md` |
| engineering-standards | ## 25. Extracting a reusable traversal/walk core | `engineering-standards/reference/layering-and-wiring.md` |
| engineering-standards | ## 26. Code Comments and Documentation | `.claude/rules/comments.md` |
| engineering-standards | ## 27. CC-local signals and shadow-mode detectors | `engineering-standards/reference/pipelines-and-plugins.md` |
| engineering-standards | ## 28. Inference budget (single-Spark deployments) | `engineering-standards/reference/pipelines-and-plugins.md` |
| front-end | ## Styling system | `front-end/reference/design-tokens.md` |
| front-end | ## Component patterns | `front-end/reference/components.md` |
| front-end | ## Data tables and pagination | `front-end/reference/components.md` |
| front-end | ## Form patterns | `front-end/reference/components.md` |
| front-end | ## DS signature components (`components/common/`) | `front-end/reference/components.md` |
| front-end | ## API and contracts | `front-end/reference/api-and-state.md` |
| front-end | ## State management | `front-end/reference/api-and-state.md` |
| front-end | ## Composables | `front-end/reference/api-and-state.md` |
| front-end | ## Testing and warning hygiene | `front-end/reference/testing-and-gates.md` |
| front-end | ## Common mistakes to avoid | `front-end/reference/common-mistakes.md` |
| front-end | ## Right-hand inspector drawer with deep enrichment | `front-end/reference/components.md` |
| front-end | ## Spatial canvas: pan/zoom and annotation standards | `front-end/reference/spatial-canvas.md` |
| front-end | ## Data visualisation / ### Authorised libraries | removed: duplicated in the data-visualization skill (catalogue, hard rules, provenance); that skill owns them |
| front-end | ## Data visualisation / ### Pipeline builder canvas (editor) | `front-end/reference/components.md` (Tracking workspace and pipeline canvas) |
| front-end | ## Data visualisation / ### Shared component catalogue | removed: duplicated in the data-visualization skill (catalogue, hard rules, provenance); that skill owns them |
| front-end | ## Data visualisation / ### Hard rules (D2/D3) | removed: duplicated in the data-visualization skill (catalogue, hard rules, provenance); that skill owns them |
| front-end | ## Data visualisation / ### Provenance and quality (D5) | removed: duplicated in the data-visualization skill (catalogue, hard rules, provenance); that skill owns them |
| front-end | ## Data visualisation / ### Tracking workspace information architecture | `front-end/reference/components.md` (Tracking workspace and pipeline canvas) |
| front-end | ## Data visualisation / ### Tracking panel-addition checklist | `front-end/reference/components.md` (Tracking workspace and pipeline canvas) |
| front-end | ## Data visualisation / ### Live process pattern | `front-end/reference/components.md` (Tracking workspace and pipeline canvas) |
| front-end | ## Alternate themes and the Marauder's Map mode | `front-end/reference/marauders.md` |
| front-end | ## File organization | `front-end/reference/testing-and-gates.md` |
| front-end | ## Adding a new admin list view | `front-end/reference/components.md` |
| front-end | ## Admin dashboard cards | `front-end/reference/components.md` |
| front-end | ## Routine Builder | `front-end/reference/components.md` |
| front-end | ## Toolchain | `front-end/reference/testing-and-gates.md` |
| front-end | ## Signal kind presentation | `front-end/reference/api-and-state.md` |
| front-end | ## Deterministic gates | `front-end/reference/testing-and-gates.md` |
| front-end | ## Verification checklist | `front-end/reference/testing-and-gates.md` |
