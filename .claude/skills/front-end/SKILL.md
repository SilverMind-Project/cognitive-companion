---
name: front-end
description: "Use when changing Cognitive Companion Vue, Vuetify, routing, Tracking workspace panels, composables, layouts, drawers, dialogs, styling, or frontend tests."
paths: ["**/frontend/**"]
---

# Front-end

The rules for every change under `frontend/`. Each rule is one line; the detail, templates, and
examples live in `reference/`. Charts and dashboards are the `data-visualization` skill; CTS
identity surfaces add the `cts-identity-admin` skill. Read a reference file when its trigger
applies:

| Read | When |
| --- | --- |
| `reference/design-tokens.md` | Writing any CSS, choosing a color, styling a Vuetify component |
| `reference/components.md` | A view, dialog, drawer, table, form, inspector, dashboard card, tracking panel, or the pipeline canvas |
| `reference/api-and-state.md` | An endpoint call, a store, or a composable |
| `reference/spatial-canvas.md` | A zoomable canvas, SVG annotation, or floor-plan view |
| `reference/marauders.md` | Theming, or anything under `components/marauders/` |
| `reference/testing-and-gates.md` | Writing tests, the toolchain, file layout, or declaring work done |
| `reference/common-mistakes.md` | Reviewing a frontend change |

## Gates (check these first)

1. Before declaring done: `npm run lint`, `npm run format:check`, `npm run typecheck`,
   `npx vitest run`, `npm run build`, `npm run knip`, and `npm audit --audit-level=high`, on the
   Node version in `frontend/.nvmrc`. `make check-all` runs them. A rule that must be relaxed is
   relaxed in `eslint.config.js` with a comment, never by inline disables.
2. The test suite is warning-clean: a `[Vue warn]` or `[Vue Router warn]` is a defect. Fix the
   harness (mount the real plugin or stub the exact boundary); never silence it.
3. Tests live under `frontend/tests/`, mirroring `src/`, importing with `@/`; never in `src/`.

## Styling

4. Colors come only from `--cc-*` tokens or Vuetify theme colors: no hex, no `rgba()`, no material
   color names (`color="green"`, `text-grey`) (`reference/design-tokens.md`).
5. One product theme, `ccWarm`, plus the isolated `ccMarauders`; no dark mode, no theme switcher.
6. Never style what `theme.css` already owns (app bar, drawers, cards, dialogs, fields); no scoped
   surface or text colors. An undefined `--cc-*` name falls back silently: check it exists.

## Components and layout

7. Detail and form modals use `AppDialog` (`sm` 480, `md` 720, `lg` 1080, `xl` 1440); a plain
   `v-dialog` + `v-card` is only for the `useConfirm()` dialog, always `persistent`.
8. Right drawers use `class="cc-drawer-right"` at width 480 or 640 only, a plain `<div>` root, and
   a `min-height: 0` scroll body.
9. Every `v-data-table` sits in `<v-card class="glass-card">`, paginates server-side
   (`:items-length`, `:page`, `@update:options`), resets to page 1 on any filter change, and uses
   `#no-data` (never `#bottom`) for the empty state; a small workbench table may skip pagination.
10. Destructive or irreversible actions (merge, split, delete, reassign) need a visible review step
    and `useConfirm()` immediately before the request; bulk mutations use one batch endpoint.
11. Use the shared controls: `CcSegmentedToggle` (never `v-btn-toggle` for pickers),
    `CcStatusPill`, `CcAvatar`, `KeyframeAnnotationDialog`, `useCanvasZoom` + `CcZoomControls`.
12. A row mixing a labeled field and a control uses `align-items: center`; fields inherit
    `outlined`/`comfortable`; submit buttons show `:loading`.
13. Route names sit on the record that resolves the page; router tests use the real table with
    `createMemoryHistory()`.

## API, state, and composables

14. All HTTP goes through `services/http.ts` and typed modules under `services/modules/`; never
    `fetch` elsewhere, never a method added to `api.js`, never a value interpolated into a URL.
15. Response types come only from the generated `api-types.d.ts`; a missing type means the backend
    route lacks `response_model`: fix it there.
16. One endpoint owns each fact: never recover a fact from another endpoint's envelope in a
    `catch`.
17. Shared state lives in Pinia stores under `src/stores/`; a module-level `ref` shared across
    components is a store and must move there. Notifications go through `useNotify()`; never a
    local `<v-snackbar>`.
18. Composables return `state` and `actions` (plus optional read-only `computed` values); never a
    raw `ref` or a function outside `actions`; one canonical key per value; test mocks reproduce
    the real return shape.
19. Composables accept a `notify` callback or expose `state.error`; they do not call `useNotify()`
    themselves.
20. Signal kinds come only from the generated vocabulary; presentation extras live in
    `constants/signalKinds.js` with a generic fallback for unknown kinds.

## Data, time, and provenance

21. Presentational panels render from props and never fetch the owner's data; `usePersonPresence`
    is the only fetch owner for person location in `TrackingWorkspace`.
22. Provenance (`confidence`, `quality`, `staleness_seconds`, `source`) is shown with
    `CcProvenanceBadge` and never computed client-side.
23. Time is formatted only with `services/timezone.js`; never `toLocaleString()` or `getHours()`.

## Spatial and themes

24. Zoomable canvases use the canonical outer/inner structure; interactive children use
    `@mousedown.stop` and honor `didPan` (`reference/spatial-canvas.md`).
25. Annotation text uses `useAnnotationStyle.js` halos at font-weight 500; rough.js shapes are
    seeded from a stable id and memoized.
26. Theme-specific code lives only in its own folder with one `v-if` per render seam; every theme
    animation has a reduced-motion fallback (`reference/marauders.md`).
