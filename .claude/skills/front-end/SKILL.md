# Frontend Engineering Skill

Guidelines for building and modifying the Cognitive Companion Vue 3 + Vuetify frontend. Every agent working on this codebase must follow these patterns.

---

## Styling system

### Design tokens (`frontend/src/styles/theme.css`)

All custom CSS properties are prefixed `--cc-` and live in three blocks:

- `:root`: brand colors, geometry radii, typography stacks (shared across themes)
- `.v-theme--ccDark`: dark-mode surface, text, border, shadow values
- `.v-theme--ccLight`: light-mode overrides for the same tokens

**Always use these variables** instead of hardcoded colors or `rgba(255,255,255,…)` values:

```css
/* Surface layering */
--cc-bg                 /* page background */
--cc-bg-elevated        /* dialog / elevated card background */
--cc-surface            /* default card glass surface */
--cc-surface-2          /* tonal / inset section surface */
--cc-surface-3          /* input field glass surface */

/* Text */
--cc-text-1             /* primary text */
--cc-text-2             /* secondary / medium-emphasis */
--cc-text-3             /* tertiary / disabled */

/* Borders */
--cc-divider            /* subtle separator */
--cc-divider-strong     /* prominent separator */
--cc-glass-border       /* card border */
--cc-glass-border-strong /* dialog card border */

/* Shadows */
--cc-shadow-sm / --cc-shadow-md / --cc-shadow-lg
--cc-shadow-glass / --cc-shadow-glass-hover

/* Radii */
--cc-radius-sm: 8px; --cc-radius-md: 12px;
--cc-radius-lg: 18px; --cc-radius-xl: 24px;
--cc-radius-pill: 980px;
```

### How frosted-glass works

The global stylesheet automatically applies frosted-glass to:
- `v-app-bar`, `v-navigation-drawer`: `backdrop-filter: saturate(200%) blur(20px)`
- All elevated `v-card` (non-outlined, non-tonal): glass surface + border + shadow
- Dialog cards (`v-dialog > .v-overlay__content > .v-card`): `--cc-bg-elevated` + 28px blur + stronger border
- Input fields (`v-field--variant-outlined`): `--cc-surface-3` + 6px blur

**Never add background-color or custom glass effects to these elements.** The global rules handle them.

### Utility classes (defined in `theme.css`)

| Class | Use |
|---|---|
| `.glass-card` | Explicit frosted-glass panel for non-Vuetify wrappers. Has hover animation. |
| `.stat-card` | Dashboard metric cards. Hover lift + border accent. |
| `.cc-inset-section` | Subtle bordered section within dialogs/cards. Uses `--cc-surface-2`. |
| `.cc-gradient-text` | Animated brand-gradient headline. Respects `prefers-reduced-motion`. |
| `.cc-code` | Inline monospace code chip. |
| `.cc-main-container` | `max-width: 1440px` centered container. |
| `.tracking-tight` | `letter-spacing: -0.018em`. Use on all page titles (`text-h4`). |

---

## Component patterns

### Router configuration

Vue Router warnings are production defects, even when tests pass.

- Layout routes with a default empty-path child (`path: ""`) must not put the route `name` on the parent if the child redirects or renders the default page. Put the name on the empty-path child when named navigation to the layout path is required.
- Route names belong on the route record that actually resolves the component or redirect users should reach. Avoid naming abstract/layout-only parents.
- Redirect-only compatibility routes may be unnamed unless code navigates to them by name. If named, the name must be unique and tested.
- Router tests use `createMemoryHistory()` and the real route table. Do not mock Vue Router when the route matching, redirect, params, query, or named-route behavior is under test.

```js
// Correct: /admin named navigation resolves the default child redirect.
{
  path: "/admin",
  component: () => import("../views/AdminView.vue"),
  children: [
    { path: "", name: "admin", redirect: "/admin/dashboard" },
    { path: "dashboard", name: "admin-dashboard", component: DashboardView },
  ],
}
```

### Page layout

Every admin list view follows this structure:

```html
<template>
  <div>
    <!-- Header row -->
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Page Title</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Brief description of what this page manages.
        </div>
      </div>
      <v-spacer />
      <!-- filter controls -->
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Item
      </v-btn>
    </div>

    <!-- Table card -->
    <v-card class="glass-card">
      <v-data-table ... />
    </v-card>

    <!-- Dialogs at the bottom of the template -->
  </div>
</template>
```

### Dialog pattern

Dialogs get glass styling automatically from the global rule. Use plain `<v-card>` with no custom class:

```html
<v-dialog v-model="showDialog" max-width="600" persistent>
  <v-card>
    <v-card-title>Title</v-card-title>
    <v-card-text>
      <!-- form fields -->
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="showDialog = false">Cancel</v-btn>
      <v-btn color="primary" :loading="saving" @click="save">Save</v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

- `max-width` is typically `400` for confirm dialogs, `600`–`640` for create/edit forms, `800` for complex editors.
- Confirm/delete dialogs use `rounded="xl"` on the inner card.
- Always use `persistent` on create/edit dialogs to prevent accidental dismissal.
- Always put the primary action on the right (`v-spacer` between Cancel and Save).

### Inset sections within dialogs

Use `<v-card variant="tonal">` for grouped sub-sections inside a dialog:

```html
<v-card variant="tonal" class="mb-4 pa-3">
  <div class="text-subtitle-2 mb-2">Section Title</div>
  <!-- section content -->
</v-card>
```

This gets `--cc-surface-2` background from the global tonal card rule. No custom classes needed.

### Right-side drawer pattern

Right-side drawers overlay the main content and must scroll independently from the page. Every `v-navigation-drawer` with `location="right" temporary` follows this structure:

```html
<v-navigation-drawer v-model="open" location="right" temporary width="480" class="cc-drawer-right">
  <v-card flat class="h-100 d-flex flex-column">
    <v-card-title class="d-flex align-center">
      Drawer Title
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
    </v-card-title>
    <!-- optional conditional content (alerts, metadata) -->
    <v-card-text v-if="condition" class="pb-0">...</v-card-text>
    <!-- optional tabs -->
    <v-tabs v-model="tab" color="primary" density="compact" class="px-4">...</v-tabs>
    <!-- scrollable body -->
    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <v-card-text>
        ...
      </v-card-text>
    </div>
  </v-card>
</v-navigation-drawer>
```

**Required CSS** (scoped to the view):

```css
.cc-drawer-right {
  position: fixed !important;
  top: 0 !important;
  bottom: 0 !important;
  height: auto !important;
}
.cc-drawer-right :deep(.v-navigation-drawer__content) {
  flex: 1 1 0;
  min-height: 0;
  padding-top: 64px;
}
```

**Rules:**

- Use `width` between `480`–`500` for content-heavy drawers, `400`–`440` for simple forms
- Always wrap content in `<v-card flat class="h-100 d-flex flex-column">`: this gives the drawer a frosted-glass card surface and sets up the flex column layout
- The `v-card` is the single root element inside the drawer; dialogs (confirm, etc.) go as siblings *outside* the card
- The title is a plain `<v-card-title>`: no custom background, border, or sticky positioning needed. It sits naturally at the top of the card as a fixed flex child
- Add `padding-top: 64px` on `.v-navigation-drawer__content`: this clears the app bar so content is not cut off
- Override `.v-navigation-drawer__content` with `flex: 1 1 0; min-height: 0` so the content area fills the drawer and handles its own overflow
- The scrollable area uses `flex-grow-1 overflow-y-auto` with `min-height: 0` so it shrinks correctly inside the flex column
- Content inside the scrollable area should use `<v-card-text>` for proper padding and to match the card surface
- Tabs, if needed, go before the scrollable area as a natural-height flex child
- Optional conditional content (status alerts, location metadata) can use `<v-card-text class="pb-0">` before the tabs

---

## Data tables and pagination

### Table visual wrapper (mandatory)

Every `v-data-table` must be wrapped in `<v-card class="glass-card">`. This gives the table the frosted-glass surface, border, and shadow consistent with all other cards in the app.

```html
<v-card class="glass-card">
  <v-data-table :headers="headers" :items="items" :loading="loading" item-value="id">
    <!-- column templates -->
  </v-data-table>
</v-card>
```

For tables that are tool/workbench views (not CRUD list views), `density="compact" hide-default-footer :items-per-page="-1"` is acceptable when the dataset is small and pagination is unnecessary. These tables still use the `glass-card` wrapper.

### Server-side pagination (mandatory for all list views)

Every `v-data-table` must use server-side pagination. The pattern:

**State variables:**
```js
const totalItems = ref(0);
const itemsPerPage = ref(20);
const page = ref(1);
```

**Table bindings:**
```html
<v-data-table
  :headers="headers"
  :items="items"
  :loading="loading"
  :items-length="totalItems"
  :items-per-page="itemsPerPage"
  :page="page"
  @update:options="onPageOptions"
>
```

**Page options handler:**
```js
function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
  if (newPerPage !== itemsPerPage.value) {
    itemsPerPage.value = newPerPage;
    page.value = 1;
  } else {
    page.value = newPage;
  }
  fetchItems();
}
```

**Fetch function passes limit/offset:**
```js
async function fetchItems() {
  loading.value = true;
  try {
    const params = {
      limit: itemsPerPage.value,
      offset: (page.value - 1) * itemsPerPage.value,
    };
    // ... add filter params
    const res = await api.getItems(params);
    items.value = res.items ?? [];
    totalItems.value = res.total ?? 0;
  } catch (err) {
    notify.error("Failed to load: " + (err.message || err));
  } finally {
    loading.value = false;
  }
}
```

**Filter changes MUST reset page to 1:**
```html
@update:model-value="page = 1; fetchItems()"
```

**Do NOT use `#bottom` template** for "No items yet" messages. When `totalItems` is 0, Vuetify shows its built-in empty state. Use `#no-data` for custom empty-state content: it renders only when there is zero data and loading is complete, without overriding the pagination footer.

**Backend pagination support is required.** The list endpoint must:
1. Accept `limit` and `offset` query params
2. Return `{ "items": [...], "total": <int> }` (not a raw array)
3. Run a `SELECT count(*)` for the unfiltered total

If the backend returns a raw array without `total`, server-side pagination cannot be wired and the table will use client-side pagination (Vuetify default). To add server-side pagination to an existing endpoint, update the router to accept `limit`/`offset` params, add a count query, and return the `{ items, total }` shape.

### Actions column width

Use `width: 200` for the Actions column when there are 4+ icon buttons (edit, approve, archive, delete). For 2–3 buttons, use the default width or omit the width prop.

### Column patterns

- Status columns: `width: 100`, use `<v-chip>` with `statusColor()` helper
- Version/ID columns: `width: 80`
- Datetime columns: import `DATETIME_COLUMN_WIDTH` from `@/services/timezone.js`
- Tag/chip-list columns (e.g. trigger types, labels): `width: 160` to constrain without truncating typical values

### Compact option selectors in page headers and table toolbars

**Do not use `v-btn-toggle`** for period/mode pickers in headers and toolbars. Vuetify's `v-btn-group` collapses the border between adjacent buttons (`border-inline-end: none`), making them visually merge into a single block. Spacing utility classes (`px-4`, `ga-*`) cannot fix this because they operate on padding/gap, not on the shared-border collapse.

Instead, render individual `v-btn` elements inside a `d-flex ga-2` container and manage active state manually:

```html
<div class="d-flex ga-2">
  <v-btn
    v-for="opt in options"
    :key="opt.value"
    size="small"
    :variant="selected === opt.value ? 'flat' : 'outlined'"
    :color="selected === opt.value ? 'primary' : undefined"
    @click="selected = opt.value"
  >{{ opt.label }}</v-btn>
</div>
```

```js
const options = [
  { value: "last_15m", label: "15m" },
  { value: "last_1h",  label: "1h"  },
  { value: "last_24h", label: "24h" },
  { value: "last_30d", label: "30d" },
];
```

This gives full gap control, keeps Vuetify's pressed/hover states, and avoids the collapsed-border problem entirely.

### Empty-state (`#no-data`) template

Every `v-data-table` must include a `#no-data` slot with a consistent empty-state message:

```html
<template #no-data>
  <div class="pa-6 text-center">
    <v-card flat>
      <v-card-text class="text-grey text-h6">No X yet</v-card-text>
      <v-card-text class="text-grey">
        Brief sentence about when data will appear.
      </v-card-text>
    </v-card>
  </div>
</template>
```

- Always use `#no-data`, never `#bottom` for empty-state messages (`#bottom` overrides the pagination footer)
- The text should be descriptive and reassuring
- The `v-card flat` keeps it visually subtle
- Use `text-grey` for both lines to match the muted empty-state aesthetic

### Tab layout pattern

For views with multiple tabs, follow this pattern (see `PersonsView.vue`):

```html
<v-tabs v-model="activeTab" color="primary" class="mb-4">
  <v-tab value="tab1">Tab Label 1</v-tab>
  <v-tab value="tab2">Tab Label 2</v-tab>
</v-tabs>

<v-window v-model="activeTab">
  <v-window-item value="tab1">
    <!-- content for tab 1 -->
  </v-window-item>
  <v-window-item value="tab2">
    <!-- content for tab 2 -->
  </v-window-item>
</v-window>
```

- Use `color="primary"` on `v-tabs` for the accent-colored active indicator
- Use `v-window` + `v-window-item` (not `v-tabs-window`) for tab content
- Filter controls within a tab should be wrapped in `<v-card variant="tonal" class="pa-2 mb-2">` for visual grouping
- The tab content tables should be inside `<v-card class="glass-card">` like a regular list view

---

## Form patterns

- All form fields inherit `variant="outlined"` and `density="comfortable"` from Vuetify defaults. Don't override unless you have a specific reason.
- In compact areas (question editors, expanded rows), use `density="compact" hide-details`.
- Use `:rules` on required fields: `[r => !!r || 'Field is required']`
- Always use `:loading` on submit buttons.
- Form state resets go in `closeCreateDialog()`: reset every field back to default.

---

## API and contracts

### Adding new API methods

Follow the existing pattern in `frontend/src/services/api.js`:
- JSON requests use the internal `request()` helper
- FormData/multipart requests use `requestForm()`
- Query params are built with `URLSearchParams`
- Every endpoint registers a contract name in `contracts.js` for dev-mode response validation

### Contracts (`frontend/src/services/contracts.js`)

Every list/detail endpoint must have a contract. Register it with:
```js
def("resource.action", { key: "type", ... });
```

Supported types: `"array"`, `"object"`, `"number"`, `"string"`, `"boolean"`, `"?"` (optional key).

---

## Composables

### `useNotify()`
```js
const { notify } = useNotify();
notify.success("Created.");
notify.error("Failed: " + err.message);
notify.warning("Validation message");
```

### `useConfirm()`
```js
const { confirmDialog, confirmTitle, confirmText, confirmLabel, cancelLabel,
        confirmColor, require: confirmRequire, onConfirm, onCancel } = useConfirm();

// For simple yes/no:
const ok = await confirmRequire("Delete this item?");
if (!ok) return;

// The confirm dialog template must be included in the view:
// <v-dialog v-model="confirmDialog" max-width="400">
//   <v-card rounded="xl"> ... </v-card>
// </v-dialog>
```

---

## Testing and warning hygiene

The frontend test suite must be warning-clean. A passing test run with `stderr` warnings is not complete.

### Treat warnings as root-cause bugs

- Fix `[Vue warn]` and `[Vue Router warn]` at the source. Do not suppress them with console spies, global filters, or `compilerOptions.isCustomElement` unless the component is truly a browser custom element.
- Do not add silent fallbacks to make tests quiet. If a component depends on Vuetify, Router, Pinia, or a provided injection, mount it with that dependency or stub the exact component boundary intentionally.
- When a warning appears only in tests, the test harness is usually incomplete. Make the harness match the runtime contract instead of changing production code.

### Component mount rules

- Prefer a small local `mountX()` helper per spec file once two tests mount the same component.
- Provide a real memory router plugin when the component calls `useRouter()`, renders `router-link`, or uses `$router` and route behavior is relevant. Mock `vue-router` only for isolated tests that do not care about routing.
- Stub Vuetify components explicitly by tag name when not installing Vuetify. Include every Vuetify tag rendered by the component and by non-stubbed children.
- Stub components with slots and the props/events the test depends on. Avoid `true` stubs for components whose rendered slot content, click events, or attributes are part of the assertion.

```js
const stubs = {
  "v-card": { template: '<section><slot /></section>', props: ["color", "variant"] },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-img": {
    template: '<img :src="src" @click="$emit(\'click\', $event)" />',
    props: ["src"],
  },
};

function mountPanel(props) {
  return mount(Panel, { props, global: { stubs } });
}
```

### Data ownership tests

For presentational panels that receive data by prop, tests must assert the ownership boundary:

- Render from the prop value.
- Do not call the service that owns the upstream fetch.
- Feed sibling panels the same fixture when testing consistency across the UI.

This is especially important for `TrackingWorkspace`: `usePersonPresence` is the single fetch owner for person-location data; workspace panels consume `locations` and must not independently call `api.getPersonLocations()`.

### Verification

Before finishing frontend test work, run at least the affected specs and one full suite pass:

```bash
cd frontend
npm run test --silent -- <affected spec paths>
npm run test -- --reporter=dot
```

The final output should contain only test results, not Vue, Vue Router, unresolved component, injection, or console warnings.

---

## Common mistakes to avoid

1. **Hardcoded `rgba(255, 255, 255, …)` colors**: these break in light mode. Use `--cc-*` variables or Vuetify named colors.
2. **Scoped `<style>` blocks with custom colors**: use global utility classes and Vuetify variants instead.
3. **Static `:items-per-page`** on data tables: use server-side pagination with `:items-length`.
4. **Not resetting `page = 1` on filter changes**: causes empty pages when filters narrow results.
5. **`item-title="title"` on layout selects**: layout objects use `display_name`, not `title`.
6. **Sending fields not in the backend schema**: check the Pydantic model for allowed fields (many schemas use `extra="forbid"`).
7. **`toLocaleString()` for dates**: use `formatDateTime` from `@/services/timezone.js`.
8. **`alert()` / `confirm()` in Vue**: use `useNotify()` / `useConfirm()`.
9. **Extra fields in PATCH requests**: PATCH schemas have `extra="forbid"`. Only send fields defined in the Update schema.
10. **Incomplete test harnesses**: unresolved Vuetify components, missing router injections, and Vue Router config warnings are defects. Mount with the right plugin or explicit stubs; never suppress the warning.
11. **Margin classes on Vuetify wrapper components inside slot templates**: `v-chip`, `v-btn`, and `v-avatar` render internal DOM wrappers that can absorb `mr-2`/`ml-2` classes, making the margin invisible. Always wrap these components in a `<div>` with the margin class when they appear in `#prepend` or `#append` slots:

    ```html
    <!-- WRONG: margin may land on an internal wrapper -->
    <template #prepend>
      <v-chip class="mr-2">Label</v-chip>
    </template>

    <!-- RIGHT: margin on a plain div is always visible -->
    <template #prepend>
      <div class="mr-2">
        <v-chip>Label</v-chip>
      </div>
    </template>
    ```

    Simple elements (`v-icon`, `<span>`) do not have this issue and can take margin classes directly. In `#prepend` slots, use `mr-2` (push content right); in `#append` slots, use `ml-2` (push content left).

---

## Right-hand inspector drawer with deep enrichment

This pattern applies to any drawer that shows detail for a selected list row and loads additional data sections lazily (observations, trail, revisions, co-present entities). Reference implementation: `PHInspectorDrawer.vue`.

### Structure rules

1. **The drawer component is a thin coordinator.** It receives the selected item as a prop, delegates all data fetching to a `useDetail` composable, and delegates all mutation to a `useCorrection` composable. It never contains inline fetch logic.

2. **Tabs split heavy sections.** Use `v-tabs` + `v-window` inside the drawer to split: Summary (always visible), Evidence/Observations (lazy), History/Revisions (lazy), Actions. This prevents loading all sections on every row click.

3. **Six-component decomposition.** For any inspector with 4+ distinct data sections, extract each section into its own component. The naming convention is `{Domain}{Section}.vue`. Example: `PHObservationsTimeline.vue`, `PHRevisionsFeed.vue`, `PHTrailMiniFloorPlan.vue`, `PHCorrectionForm.vue`, `PHPeopleSummary.vue`, `PHListPanel.vue`. Do not inline these sections in the drawer.

4. **Confirmation on all destructive actions.** Any action that is hard to reverse (merge, split, delete, reassign) must call `useConfirm()` before proceeding. Never allow an irreversible action without a dialog confirmation.

5. **`useNotify()` for all outcomes.** Success, warning, and error states surface via `useNotify()`, not `console.log` or native `alert()`.

6. **Row click wires `@click:row`, not just a button.** On `v-data-table-server`, add both:
   - `@click:row="(_event, { item }) => openDrawer(item)"` for the full-row click
   - `hover` prop to show pointer cursor
   - A dedicated Inspect button inside `#item.actions` that calls `event.stopPropagation(); openDrawer(item)` to avoid double-open

7. **All time in the drawer uses `services/timezone.js`.** Never `new Date().toLocaleString()` or raw `Date` methods.

### Template skeleton

```html
<v-navigation-drawer v-model="open" location="right" temporary width="500" class="cc-drawer-right">
  <v-card flat class="h-100 d-flex flex-column">
    <!-- Fixed header -->
    <v-card-title class="d-flex align-center py-3">
      <PHListPanel :item="selectedItem" />
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
    </v-card-title>

    <!-- Optional alert banner -->
    <v-card-text v-if="state.error" class="pb-0">
      <v-alert type="error" density="compact">{{ state.error }}</v-alert>
    </v-card-text>

    <!-- Tabs -->
    <v-tabs v-model="tab" color="primary" density="compact" class="px-4">
      <v-tab value="summary">Summary</v-tab>
      <v-tab value="observations">Observations</v-tab>
      <v-tab value="history">History</v-tab>
      <v-tab value="actions">Actions</v-tab>
    </v-tabs>

    <!-- Scrollable body -->
    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <v-card-text>
        <v-window v-model="tab">
          <v-window-item value="summary">
            <PHTrailMiniFloorPlan :trail-points="state.trail" />
            <PHPeopleSummary :co-present="state.coPresent" />
          </v-window-item>
          <v-window-item value="observations">
            <PHObservationsTimeline :item-id="selectedItem.id" />
          </v-window-item>
          <v-window-item value="history">
            <PHRevisionsFeed :item-id="selectedItem.id" />
          </v-window-item>
          <v-window-item value="actions">
            <PHCorrectionForm :item-id="selectedItem.id" @corrected="onCorrected" />
          </v-window-item>
        </v-window>
      </v-card-text>
    </div>
  </v-card>

  <!-- Confirmation dialogs outside the card but inside the drawer -->
  <v-dialog v-model="confirmDialog" max-width="400">
    <v-card rounded="xl">
      <v-card-title>{{ confirmTitle }}</v-card-title>
      <v-card-text>{{ confirmText }}</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
        <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</v-navigation-drawer>
```

Required scoped CSS (same as right-side drawer pattern):
```css
.cc-drawer-right {
  position: fixed !important;
  top: 0 !important;
  bottom: 0 !important;
  height: auto !important;
}
.cc-drawer-right :deep(.v-navigation-drawer__content) {
  flex: 1 1 0;
  min-height: 0;
  padding-top: 64px;
}
```

---

## Data visualisation

### Authorised libraries

- **`echarts` + `vue-echarts`**: the only permitted charting library. Use explicit module imports only; never import the full ECharts bundle.
- No second charting or flow-diagram library. No hand-rolled SVG charts for data shapes covered by the shared components.

### Shared component catalogue

All chart and dashboard components live in `frontend/src/components/`. Use them; never duplicate their logic in a view.

**Charts (`components/charts/`)**

| Component | Data shape | When to use |
|-----------|-----------|-------------|
| `CcTimeSeriesChart.vue` | Time-indexed numeric series | Presence trends, signal history, motion energy |
| `CcBarChart.vue` | Categorical bars | Room dwell totals, signal counts by kind |
| `CcDistributionChart.vue` | Histogram / distribution | Quality score distribution, dwell-duration spread |
| `CcGaugeChart.vue` | Single scalar 0-100 | Mean quality gauge, confidence indicator |
| `CcHeatmapCalendar.vue` | Day x hour intensity grid | Activity calendars, pacing heat maps |
| `CcScatterFloorCloud.vue` | (x, y) floor-plane points | Trajectory scatter on floor plan |

**Dashboard (`components/dashboard/`)**

| Component | Purpose |
|-----------|---------|
| `CcMetricTile.vue` | Single KPI tile with label, value, trend arrow |
| `CcProvenanceBadge.vue` | Source/quality badge rendered from `source` + `quality` envelope fields |
| `CcSectionCard.vue` | Frosted-glass section wrapper with optional header slot |

**Process (`components/process/`)**

| Component | Purpose |
|-----------|---------|
| `CcDagChart.vue` | Pipeline step DAG for live and historical runs |
| `CcLiveActivityFeed.vue` | Scrolling event feed (ingest events, signal triggers) |
| `CcStatusTimeline.vue` | Horizontal step timeline with elapsed-ms labels |

### Hard rules (D2/D3)

1. **One shared component per data shape.** If a view needs a time series chart, use `CcTimeSeriesChart`. Do not write an inline ECharts option object in a view component.
2. **Bespoke canvas only for spatial domains.** Floor plan overlays and bounding-box-on-keyframe rendering are the only permitted SVG/Canvas surfaces. They must use `useChartTheme` and `--cc-` tokens.
3. **Always use `useChartTheme`.** The composable at `composables/useChartTheme.js` injects the ECharts theme derived from Vuetify's current theme. Pass its `theme` return value to every `v-chart` instance.

```js
// CORRECT
import { useChartTheme } from '@/composables/useChartTheme.js'
const { theme } = useChartTheme()
// <v-chart :theme="theme" :option="option" />

// WRONG: hardcoded theme name or no theme
// <v-chart option={option} />
```

### Provenance and quality (D5)

Confidence, quality, staleness, and source fields travel from CTS through the BFF envelope to the UI as explicit fields. The UI **never computes them client-side**.

Always use `CcProvenanceBadge` to display source information. Pass the `source` and `quality` fields directly from the envelope:

```html
<CcProvenanceBadge :source="location.source" :quality="location.quality" :staleness-seconds="location.staleness_seconds" />
```

### Tracking workspace information architecture

The `TrackingWorkspace.vue` view is the single role-aware tracking dashboard. It uses `usePersonPresence` as the one composable for all person-location data (design rule D1). Rules:

- Do not create a second composable that fetches person location data.
- Panel visibility is controlled by permissions; do not duplicate panels into separate views for different roles.
- Add new panels as children of `TrackingWorkspace`, not as new top-level views.

### Live process pattern

Use `useLivePipeline` from `composables/useLivePipeline.js` for any component that shows live pipeline execution state.

```js
import { useLivePipeline } from '@/composables/useLivePipeline.js'
const { state, actions } = useLivePipeline()
// state.connectionStatus: 'connecting' | 'connected' | 'disconnected'
// state.activeRuns: PipelineRunEnvelope[]
// actions.connect() / actions.disconnect()
```

Connection-state rendering rules:
- **Connecting**: show a loading spinner, no run data.
- **Connected**: show live run DAGs via `CcDagChart`.
- **Disconnected**: show the last known state with a reconnection badge. **Never show stale data as live.**

`useLivePipeline` manages reconnection internally with 3-second exponential backoff. Do not implement reconnection in the view.

## File organization

```
frontend/src/
  styles/theme.css          -- global design tokens + Vuetify overrides
  services/api.js           -- all API calls
  services/contracts.js     -- response shape validation
  services/timezone.js      -- datetime formatting + constants
  composables/useNotify.js  -- snackbar notifications
  composables/useConfirm.js -- promise-based confirmation dialog
  components/common/        -- reusable shared components (LlmModelPicker, etc.)
  components/pipeline/      -- rule pipeline builder components
  components/companion/     -- senior-facing companion UI
  views/admin/              -- admin dashboard views (one per resource)
```

---

## Adding a new admin list view

1. Create `frontend/src/views/admin/NewResourceView.vue`
2. Follow the page layout pattern (header row + glass-card + table + dialogs)
3. Add API methods to `api.js` with contract names
4. Add contracts to `contracts.js`
5. Wire the route in the router config
6. Add to the admin nav drawer in `AdminView.vue`
7. Add `auth.yaml` entries for each new endpoint
8. Ensure server-side pagination with `:items-length` + `:page` + `@update:options`

---

## Verification checklist

Before marking frontend work complete:
- `cd frontend && npm run build` passes
- No hardcoded `rgba(255,255,255,…)` or hex colors in new code
- No scoped `<style>` blocks with custom colors (utility-only scoped styles are OK)
- Data tables use server-side pagination
- Dialogs use `<v-card>` without custom classes
- Form resets in close dialogs
- `tracking-tight` on page titles
- Status chips use `statusColor()` helper
- Filter changes reset page to 1
- No `getHours()`, `getMinutes()`, `getSeconds()`, `toLocaleString()`, `toLocaleDateString()`, `toLocaleTimeString()` anywhere; use `services/timezone.js`
- Inspector drawers: `useNotify()` imported and used (zero `console.log` / `console.error` stubs)
- Inspector drawers: `useConfirm()` called before every destructive action
- Inspector drawers: `@click:row` wired on data tables (not only the Inspect button)
- Composables return `{ state, actions }` shape (never flat named refs)
- When tests are touched: affected specs and `npm run test -- --reporter=dot` pass with no Vue, Vue Router, unresolved component, missing injection, or console warnings
