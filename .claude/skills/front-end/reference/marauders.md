# Alternate themes and Marauder's Map mode

Read before changing theming or anything under `components/marauders/`. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Alternate themes and the Marauder's Map mode

The app supports a third registered Vuetify theme, `ccMarauders`, that re-skins the entire admin UI to a parchment / hand-drawn Marauder's Map aesthetic. This section documents the patterns introduced by that feature so future theme work follows the same approach.

### Theme-token discipline (the re-skinnability invariant)

Every surface in the app reads `--cc-*` design tokens or Vuetify theme colors, never hardcoded hex or `rgba()` values. This discipline makes whole-app re-theming possible without per-component branching.

Adding a new full-app theme requires two steps:

1. Register a Vuetify theme in `main.js` with a `colors` object. This drives Vuetify's own `--v-theme-*` internals (buttons, switches, inputs, and chips read these, not `--cc-*`).
2. Override `--cc-*` tokens in a dedicated `.v-theme--<name> {}` block in a new stylesheet. Import that stylesheet unconditionally in `main.js` alongside `theme.css`.

Do not use a body-class alternative such as `body.marauders-mode`. A body class can only rewrite `--cc-*` tokens; Vuetify component internals read `--v-theme-*` variables, which a body class cannot set. A registered theme covers both layers.

Reference implementation: `frontend/src/main.js` (the `ccMarauders` entry in `createVuetify`) and `frontend/src/styles/marauders.css` (the `.v-theme--ccMarauders {}` block).

### The marauders isolation boundary

All Marauder's-specific render code lives in dedicated files. The only edits to existing files were: theme registration in `main.js`, a few tokenization fixes in `theme.css`, mounting the toggle and global SVG defs in `AdminView.vue`, and one `v-if` per render seam in `CTSFloorPlanView.vue`. New theme work must follow the same pattern: one `v-if` per seam; if a seam needs more than one branch, extract the themed variant as a sibling component under `components/marauders/`.

Shipped file inventory:

| File | Purpose |
|------|---------|
| `composables/useMaraudersMode.js` | Single state owner: boolean flag, `localStorage` persistence, Vuetify theme capture and restore, `reducedMotion` exposure |
| `composables/useRoughSketch.js` | rough.js path generation: seeded, memoized, with `seedFrom()` helper |
| `composables/useFootprintTrail.js` | Footprint trail state: position buffer, decay timing, reduced-motion fallback |
| `styles/marauders.css` | `.v-theme--ccMarauders {}` token block -- the sole location for parchment token overrides |
| `components/marauders/MaraudersToggle.vue` | App-bar toggle control |
| `components/marauders/MaraudersFloorMarkers.vue` | Footstep markers and trails coordinator |
| `components/marauders/MaraudersFootprintGlyph.vue` | Single footstep glyph |
| `components/marauders/MaraudersAmbientLayer.vue` | Decorative ambient-whimsy layer (clearly non-clinical) |
| `components/marauders/MaraudersHeatmapLayer.vue` | Themed heatmap presence stain layer |
| `components/marauders/MaraudersInkPolygon.vue` | Hand-drawn room polygon |
| `components/marauders/MaraudersInkBox.vue` | Hand-drawn bounding box |
| `components/marauders/MaraudersImageFilterDefs.vue` | Global SVG filter `<defs>` sprite for painterly images |
| `components/marauders/MaraudersAdminBackground.vue` | Parchment background texture layer for the admin shell |
| `assets/marauders/footstep.svg` | Footstep glyph sprite |

### The single state owner

`useMaraudersMode()` is the only owner of the mode flag and the Vuetify theme capture/restore logic. No component reads `localStorage` for the mode flag directly.

| `localStorage` key | Value | Meaning |
|--------------------|-------|---------|
| `cc_marauders` | `"1"` | Marauder's mode is active |
| `cc_marauders` | `"0"` | Marauder's mode is off |
| `cc_theme` | `"ccWarm"` or `"ccMarauders"` | The active Vuetify theme; `main.js` reads it at startup |

On enable, the composable captures the current theme name as the restore target before switching to `ccMarauders`. On disable, it restores that captured value so toggling off always returns the user to their prior `ccDark` / `ccLight` preference.

The composable returns the standard `{ state, actions }` shape:

```js
const { state, actions } = useMaraudersMode();
// state.enabled       -- boolean; true when ccMarauders is active
// state.reducedMotion -- reactive mirror of prefers-reduced-motion media query
// actions.enable(), actions.disable(), actions.toggle()
```

`state.reducedMotion` updates reactively when the media query fires. Animated components (footprints, ink draw-on, gradient shimmer) consume this flag and render a static fallback when it is true.

### Reduced-motion and accessibility for themes

Every animation introduced by an alternate theme must have a static fallback when `state.reducedMotion` is true. Query the value from `useMaraudersMode()` in the component rather than duplicating the media-query listener.

The parchment palette shipped in `marauders.css` was verified against WCAG AA at the following values:

| Text token | Background | Ratio | Result |
|-----------|-----------|-------|--------|
| `--cc-text-1` (#3a2a16) | `--cc-bg` (#e9dcc0) | 9.5:1 | AA pass |
| `--cc-text-1` (#3a2a16) | `--cc-surface` (#f0e6cf at 82%) | 9.1:1 | AA pass |
| `--cc-text-2` (#5a4326) | `--cc-bg` (#e9dcc0) | 6.3:1 | AA pass |
| `--cc-text-2` (#5a4326) | `--cc-surface` (#f0e6cf at 82%) | 6.0:1 | AA pass |
| on-primary (#f0e6cf) | primary (#5b3a1a) | 6.8:1 | AA pass |

If the palette is adjusted in future work, re-verify these ratios. WCAG AA is a floor, not a target; this is a care product.
