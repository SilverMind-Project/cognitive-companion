---
name: data-visualization
description: How to present a new data shape in the Cognitive Companion Vue UI: pick the right shared component, theme via useChartTheme, render empty/loading/error states, and never hand-roll a chart.
---

# Data Visualisation

This skill covers how to add charts and data displays to the Cognitive Companion admin interface correctly. All charts use ECharts through the shared component library; no view may hand-roll a chart of a data shape already covered by a shared component.

## Authorised stack

- **`echarts`**: the charting engine. Always use explicit module imports; never import the full bundle.
- **`vue-echarts`**: the Vue 3 wrapper. Import via `import VChart from 'vue-echarts'`.
- **`@vue-flow/core`**: permitted only for the interactive pipeline editor canvas. Not a charting
  library; serves workflow authoring. ECharts (`CcDagChart`) handles all read-only monitoring.
- **No second charting library.** No `chart.js`, `d3`, `recharts`, or similar.
- **`useChartTheme`**: the theme composable. Pass its `theme` to every `v-chart` instance.

## Shared component catalogue

### Charts (`components/charts/`)

Choose the component that matches your data shape. Never roll an equivalent inline.

| Component | Prop contract | Use when |
|-----------|---------------|----------|
| `CcTimeSeriesChart.vue` | `:series` (array of `{name, data: [{timestamp, value}]}`), `:unit` | Presence trends, motion energy over time, signal history |
| `CcBarChart.vue` | `:categories` (string[]), `:series` (array of `{name, data: number[]}`) | Room dwell totals per day, signal counts by kind |
| `CcDistributionChart.vue` | `:data` (`{label, count}[]`) | Quality score distribution, dwell-duration histogram |
| `CcGaugeChart.vue` | `:value` (0-100), `:label` | Mean quality gauge, confidence indicator |
| `CcHeatmapCalendar.vue` | `:data` (`{date, value}[]`), `:year` | Activity calendars, weekly pacing heat maps |
| `CcScatterFloorCloud.vue` | `:points` (`{x, y, label}[]`) | Trajectory scatter on floor plan (non-interactive overlay) |

### Dashboard (`components/dashboard/`)

| Component | Props | Use when |
|-----------|-------|----------|
| `CcMetricTile.vue` | `:label`, `:value`, `:trend` (`up`/`down`/`flat`) | KPI tiles in a dashboard summary row |
| `CcProvenanceBadge.vue` | `:source`, `:quality`, `:staleness-seconds` | Displaying data quality next to a location or signal value |
| `CcSectionCard.vue` | `#header` slot (optional), `#default` slot | Frosted-glass section wrapper |

### Process (`components/process/`)

| Component | Props | Use when |
|-----------|-------|----------|
| `CcDagChart.vue` | `:steps` (`PipelineRunEnvelope.steps`), `:status` | Live or historical pipeline execution DAG |
| `CcLiveActivityFeed.vue` | `:events` (feed items with `timestamp`, `label`, `kind`) | Scrolling live event feed for ingest activity, signal triggers |
| `CcStatusTimeline.vue` | `:steps` (with `label`, `status`, `elapsed_ms`) | Horizontal step timeline for a completed run |

## How to add a new chart

### 1. Pick the right component

Find the component from the table above whose data shape matches yours. If no existing component fits:
- Confirm no existing component can be adapted with a new prop.
- If genuinely new, create the component in the appropriate `components/` subdirectory following the patterns in existing components.
- Never hand-roll an ECharts option object inside a view component.

### 2. Apply the theme

```js
// In your view or component
import { useChartTheme } from '@/composables/useChartTheme.js'
const { theme } = useChartTheme()
```

```html
<!-- In template -->
<CcTimeSeriesChart :theme="theme" :series="series" unit="minutes" />
<!-- Or if using v-chart directly in a new component -->
<v-chart :theme="theme" :option="option" autoresize />
```

Never hardcode `theme="dark"` or `theme="light"` or omit the theme prop.

### 3. Render loading and empty states

Every data-driven chart must handle three states:

```html
<template>
  <CcSectionCard>
    <template #header>Presence Timeline</template>

    <!-- Loading -->
    <div v-if="state.loading" class="d-flex justify-center pa-6">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-else-if="state.error" type="error" density="compact" class="ma-4">
      {{ state.error }}
    </v-alert>

    <!-- Empty -->
    <div v-else-if="!state.series.length" class="pa-6 text-center text-medium-emphasis">
      No data for this period.
    </div>

    <!-- Chart -->
    <CcTimeSeriesChart v-else :theme="theme" :series="state.series" unit="min" />
  </CcSectionCard>
</template>
```

### 4. Wire the composable

Follow the `{ state, actions }` composable shape:

```js
// composables/usePresenceTimeline.js (example)
export function usePresenceTimeline() {
  const state = reactive({ series: [], loading: false, error: null })

  async function fetchTimeline(personId) {
    state.loading = true
    state.error = null
    try {
      const data = await api.getPresenceTimeline(personId)
      state.series = data.series
    } catch (e) {
      state.error = e.message
    } finally {
      state.loading = false
    }
  }

  return { state, actions: { fetchTimeline } }
}
```

### 5. Display quality and provenance (D5)

Whenever the data has a `quality`, `confidence`, `source`, or `staleness_seconds` field from a `PersonLocationEnvelope`, display it with `CcProvenanceBadge`. Never compute these values client-side.

```html
<CcProvenanceBadge
  :source="location.source"
  :quality="location.quality"
  :staleness-seconds="location.staleness_seconds"
/>
```

## Spatial domains: the bespoke canvas exception

Floor-plan overlays and bounding-box-on-keyframe rendering are the only cases where SVG or Canvas code is permitted outside of a shared component. Even there:

1. Import and use `useChartTheme` for color tokens.
2. Use `var(--cc-*)` CSS variables for all colors; never hardcode hex.
3. The bespoke canvas component must live in `components/` (not inline in a view).
4. Write a Vitest test that verifies the component mounts without throwing.

## Testing visual components

Visualization tests must be warning-clean. A chart or panel test that passes while Vue prints unresolved component, missing injection, or router warnings is incomplete.

### Mount with the real runtime contract

- If the component uses Router (`useRouter`, `$router`, `router-link`, route query state), mount it with a `createMemoryHistory()` router unless routing is explicitly mocked for an isolated unit.
- If the component renders Vuetify tags without installing Vuetify, stub every rendered Vuetify component by tag name. Include components rendered in non-stubbed child slots.
- Stubs must preserve the behavior under test: slots, display text, critical props, and emitted click/input events. Avoid `true` stubs when assertions depend on rendered children or attributes.
- Never quiet chart or Vue warnings by spying on `console.warn`, configuring `isCustomElement` for Vuetify tags, or swallowing errors in the component.

```js
const stubs = {
  "v-card": { template: "<section><slot /></section>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-progress-circular": { template: "<div />" },
};

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/", component: { template: "<div />" } }],
});
await router.push("/");
await router.isReady();

mount(VisualPanel, { global: { plugins: [router], stubs } });
```

### Prove data ownership

Dashboard and tracking panels should render data supplied by their owning workspace/composable. Tests for these panels must verify the visual result and the boundary:

- Use one fixture and feed it to sibling panels when checking consistency.
- Assert the panel renders labels, values, rooms, quality, and provenance from props or the owning composable state.
- Assert presentational panels do not call the API fetch that belongs to the workspace/composable.
- Do not add a fallback fetch inside a panel to make an empty chart look populated; fix the upstream data flow.

For `PersonLocationEnvelope` data, `TrackingWorkspace` and `usePersonPresence` own fetching. Visualization panels consume `locations` and display `CcProvenanceBadge` from envelope fields.

### ECharts and canvas test boundaries

- Shared chart component tests can stub `vue-echarts`/`v-chart` to inspect the computed option object, but must still assert `theme` is passed from `useChartTheme`.
- View tests should stub shared chart components instead of reaching into ECharts internals.
- Canvas/SVG spatial tests should verify mount, coordinate projection, empty state, and representative rendered markers; they should not depend on pixel-perfect snapshots unless the rendering contract requires it.

## Verification checklist

Before marking frontend visualisation work complete:

- `cd frontend && npm run build` passes with no type errors.
- No inline ECharts `option` objects in view files.
- No second charting library imported anywhere (`grep -r "chart.js\|recharts\|d3" frontend/src/`).
- `useChartTheme` is called and its `theme` is passed to every `v-chart` or chart component.
- Loading, error, and empty states are rendered explicitly.
- `CcProvenanceBadge` is used wherever a `PersonLocationEnvelope` quality field is shown.
- Spatial canvas components are in `components/`, not inlined in views.
- Affected specs and the full suite pass with no Vue, Vue Router, unresolved component, missing injection, or console warnings.
- `npm run test -- --reporter=dot` is clean when warnings were part of the work.
