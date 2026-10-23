# Spatial canvases

Read before changing a zoomable canvas, SVG annotation, or floor-plan view. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Spatial canvas: pan/zoom and annotation standards

### `useCanvasZoom`: the one zoom composable

All zoomable canvases in the app use `useCanvasZoom` from `composables/useCanvasZoom.js`. Do not implement custom zoom logic. The composable provides:

```js
const { state, containerToLocal, actions } = useCanvasZoom({
  minZoom: 0.2,  // default
  maxZoom: 6,    // default; use 5 for floor-plan live view
  wheelStep: 0.08,
  panThreshold: 3,
});
// state.zoom, state.panX, state.panY, state.transformStyle (CSS string)
// state.didPan: true after a drag exceeds panThreshold; cleared by startPan()
// actions.onWheel(e), startPan(e), zoomIn(containerRef), zoomOut(containerRef), reset()
```

#### Canonical structure for every zoomable canvas

```html
<!-- outer: clips content, catches wheel events -->
<div ref="outerRef" class="my-canvas" @wheel.prevent="zoom.actions.onWheel">

  <!-- inner: receives the CSS transform -->
  <div :style="zoom.state.transformStyle" @mousedown="zoom.actions.startPan">
    <!-- image / SVG content here -->
    <!-- Interactive child elements MUST use @mousedown.stop to prevent
         bubbling to the inner div (otherwise a drag on a vertex arms pan).
         Their click handlers check zoom.state.didPan before acting. -->
  </div>

  <!-- CcZoomControls: position:absolute, bottom-right of outerRef.
       Uses @mousedown.stop @click.stop so buttons never arm pan. -->
  <CcZoomControls
    :zoom="zoom.state.zoom"
    :pan-x="zoom.state.panX"
    :pan-y="zoom.state.panY"
    @zoom-in="zoom.actions.zoomIn(outerRef)"
    @zoom-out="zoom.actions.zoomOut(outerRef)"
    @reset="zoom.actions.reset()"
  />
</div>
```

**Outer container CSS requirements:**
```css
.my-canvas {
  position: relative;  /* anchor for CcZoomControls */
  overflow: hidden;    /* clip zoomed/panned content */
}
```

#### Interaction model (the "didPan" contract)

`startPan` is called on the inner wrapper's `@mousedown` for **every** mousedown. The 3px threshold gate prevents accidental pans from short taps. Interactive elements (vertex dots, crop handles, PHMarkers) use `@mousedown.stop` to prevent bubbling, keeping their own drag logic self-contained.

Click handlers that place points or navigate must guard against pan drags:

```js
function onSvgClick(e) {
  if (zoom.state.didPan) { zoom.state.didPan = false; return; }
  // ...place vertex / navigate
}
```

Never skip calling `startPan` for a mousedown in order to "avoid pan on this element"; that leaves `didPan` stale from a prior drag and swallows the next real click. Use `.stop` on child elements instead.

### `CcZoomControls`: the one zoom control UI

```html
<CcZoomControls
  :zoom="zoom.state.zoom"
  :pan-x="zoom.state.panX"
  :pan-y="zoom.state.panY"
  :min-zoom="0.2"   <!-- optional, matches useCanvasZoom default -->
  :max-zoom="6"     <!-- optional -->
  @zoom-in="zoom.actions.zoomIn(outerRef)"
  @zoom-out="zoom.actions.zoomOut(outerRef)"
  @reset="zoom.actions.reset()"
/>
```

The component uses global CSS classes `.cc-zoom-controls` and `.cc-zoom-pct` defined in `theme.css`. Do not add scoped CSS for these classes; they are global utilities.

Never render the four buttons (plus, minus, reset, pct chip) inline in a view or component; always use `CcZoomControls`.

### Tokens in SVG: `var(--cc-x)` resolves in presentation attributes

`var()` resolves in SVG **presentation attributes**, not only in the `style` attribute, in the browsers this app targets (verified). Both forms are valid and render identically:

```html
<text fill="var(--cc-chart-axis-label)">…</text>          <!-- presentation attribute: OK -->
<rect style="fill: var(--cc-brand-soft); stroke: var(--cc-brand)" />  <!-- style attribute: also OK -->
<line :stroke="cond ? 'var(--cc-success)' : 'var(--cc-chart-2)'" />   <!-- bound attribute: a string is a string, OK -->
```

Do **not** "fix" the `fill="var(--cc-x)"` attribute form into the `style=` form -- it is not a bug. Use whichever reads cleaner; for per-element dynamic colors, bind the attribute (`:stroke`/`:fill`) to a token string. For colors computed in JS (canvas/`ctx`), read the token value with `ccToken('--cc-x')` from `useChartTheme.js` instead.

For SVG over a photo/map background, prefer the DS chart/semantic tokens and keep distinct line/region types on distinct hues (e.g. success / chart-2 / info / text-3); the white-text + dark-halo label convention is owned by `useAnnotationStyle.js` (below).

### Canvas annotation style: `useAnnotationStyle.js`

All spatial renderers (floor plan, calibration view, live bbox overlay) share a single annotation style composable at `composables/useAnnotationStyle.js`. Import from here; never hardcode annotation colors or duplicate the halo pattern.

#### Two label contexts: camera vs. floor-plan

| Context | Background | Standard | Composable export |
|---------|-----------|----------|----------|
| Camera / video feed | Photographic (dark or mixed) | White text, thin dark halo | `HALO` |
| Floor-plan map | Architectural drawing (typically light) | Dark slate text, thin white halo | `MAP_LABEL` |

```js
import { HALO, MAP_LABEL, qualityColor, MARKER, postureColor } from '@/composables/useAnnotationStyle.js';

// Spread on SVG <text> via v-bind. Match strokeWidth to font-size × 15%.
const cameraHalo = HALO.attrs(8);     // camera-resolution SVG (font ≈ 48 SVG units)
const mapHalo    = MAP_LABEL.attrs(); // floor-plan SVG (default strokeWidth 2)
```

#### Font-weight: always 500 (medium)

Bold (700) is never used on canvas annotation text. Bold + halo distorts letter shapes and creates blocky, unreadable text. Use `font-weight="500"` on all `<text>` elements in spatial canvases.

#### Camera-feed labels (CTSLiveView, CTSCalibrationView)

```html
<text
  v-bind="HALO.attrs(strokeWidth)"
  fill="white"
  font-weight="500"
  :font-size="labelFontSize(cam)"
>{{ label }}</text>
```

For dynamic stroke-width in the live overlay:
```js
// ~15% of font-size, minimum 2 SVG units
function labelHaloStroke(cam) {
  return Math.max(2, Math.round(labelFontSize(cam) * 0.15));
}
```

For :style bindings (Vue camelCase), use `HALO.color` directly:
```js
:style="{ paintOrder: 'stroke', stroke: HALO.color, strokeWidth: labelHaloStroke(cam), strokeLinejoin: 'round' }"
```

#### Floor-plan labels (PHMarker, room labels)

```html
<text
  v-bind="MAP_LABEL.attrs()"
  font-weight="500"
  :font-size="MARKER.labelSize"
>{{ label }}</text>
```

The color identity is carried by the dot, not the text. `MAP_LABEL.attrs()` already includes `fill: "#1e293b"`.

#### Other exports

| Export | Type | Purpose |
|--------|------|---------|
| `qualityColor(residualM)` | function | Calibration residual metres → `--cc-success/warning/error` token |
| `MARKER` | const | PHMarker geometry: `outerR=18, innerR=9, labelSize=14, postureSize=11` (floor-plan px) |
| `postureColor(posture)` | function | Posture string → semantic color (standing/sitting/walking/lying) |

#### Canvas annotation tokens (`theme.css`)

```css
/* In :root; theme-invariant, designed for image/map backgrounds */
--cc-annotation-unknown:  #fb923c;   /* tracking entity with no identity */
--cc-annotation-pending:  #f59e0b;   /* point placed, awaiting second click */
--cc-annotation-halo:     rgba(0, 0, 0, 0.55);
```

### rough.js and procedural sketch generators

When rough.js or another procedural sketch library is used in a spatial component, follow these rules to prevent visual shimmer and unnecessary recomputation:

- **Seed every shape.** Pass a stable `seed` value keyed to the entity or geometry identifier (room name, bounding-box track ID, footprint index). rough.js reseeds its randomness on every call; a shape that re-renders per animation frame will shimmer visibly if the seed changes between frames. Use `useRoughSketch.js`'s `seedFrom(str)` helper to derive a numeric seed from a string identifier.
- **Memoize generated paths.** Generated SVG paths must be keyed and cached so zoom and pan do not trigger a redraw. `useRoughSketch.js` maintains a bounded LRU memo keyed on `seed + serialized vertices`. Apply the CSS transform to the SVG container, not to individual paths.
- **Use plain straight lines during interactive drag.** Sketch rendering is for committed display state. While a vertex or zone boundary is being dragged, render straight lines. Apply the sketchy style only when the geometry is committed (on `mouseup` or after the drag animation settles).

```js
import { useRoughSketch } from '@/composables/useRoughSketch.js';
const { state: rough, actions: roughActions } = useRoughSketch();

// Derive a stable numeric seed from a string identifier
const seed = roughActions.seedFrom(roomName);
// Returns a memoized SVG path string; safe to call in a computed property
const pathData = roughActions.path(polygonPoints, { seed, roughness: 1.2 });
```

This rule applies to all components under `components/marauders/` and any future spatial component that uses procedural sketch rendering.

### Floor plan live view sizing

The live canvas uses `aspect-ratio` CSS (not fixed `min-height`) so it correctly proportions to the floor plan image:

```html
<div
  class="floor-plan-canvas"
  :style="{ aspectRatio: `${canvasW}/${canvasH}`, maxHeight: '65vh' }"
>
```

This prevents the "tightly compacted" issue where a tall or wide floor plan was letter-boxed into a fixed-height box.
