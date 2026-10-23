# Component patterns

Read before building a view, dialog, drawer, table, form, inspector, dashboard card, or tracking panel. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Component patterns

### Human-interface baseline

Follow the durable parts of Apple Human Interface Guidelines and Google Material Design:

- Prefer recognition over recall. Caregivers should choose from visible tracks, identities, thumbnails, and labels; do not ask them to paste opaque IDs unless the ID is also easy to copy from the same workflow.
- Keep destructive and irreversible actions explicit. Bulk delete, merge, split, and identity reassignment require a visible review step and a `useConfirm()` confirmation before the mutation request is sent.
- Maintain layout stability. Drawers and dialogs must overlay content without resizing the primary work surface. Filter bars and table columns need stable dimensions so data does not jump as values change.
- Reuse established controls. Use the shared dialog/header/editor components before creating a one-off surface; one task should not have multiple visual languages.
- Progressive disclosure beats empty panels. Detail drawers should show the best available evidence first: identity label, short PH ID, room/camera, recent keyframes, and timestamp context.

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

Dialogs use a solid elevated surface (`--cc-bg-elevated`), not the `--cc-surface` used by cards. Detail and form modals use `AppDialog` (next section); the plain `v-dialog` + `<v-card>` below is for the `useConfirm()` confirmation dialog only:

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
- **Never add opacity or translucency to dialog cards.** Dialogs must be ≥95% opaque so the content behind does not bleed through.

#### CSS specificity note (do not regress)

`theme.css` has a global card rule at specificity (0,6,0) that applies `--cc-surface`. The dialog override sits at specificity (0,8,0) -- it repeats the `:not()` chain to win with `!important`. If you ever add more `:not()` exclusions to the global card rule, add the same exclusion to the dialog rule so the dialog keeps `--cc-bg-elevated`.
- Always put the primary action on the right (`v-spacer` between Cancel and Save).

### Detail modals: use `AppDialog`

Use `AppDialog` for any medium/large detail modal; pick `size` from the preset table; never hand-roll a `v-dialog` + `v-card` + header/footer.
`DialogHeader`/`DialogFooter` are the building blocks; `AppDialog` composes them.
Migrate legacy `v-dialog`s to `AppDialog` opportunistically when touching a file.
Tokens only; `cc-glass`; fullscreen on mobile; scrollable.

| size | width | use |
| --- | --- | --- |
| `sm` | 480 | confirmations, single-field edits |
| `md` | 720 | standard detail forms (default) |
| `lg` | 1080 | rich detail / multi-column |
| `xl` | 1440 | canvas / workbench (matches `StepConfigDialog`) |

### Inset sections within dialogs

Use `<v-card variant="tonal">` for grouped sub-sections inside a dialog:

```html
<v-card variant="tonal" class="mb-4 pa-3">
  <div class="text-subtitle-2 mb-2">Section Title</div>
  <!-- section content -->
</v-card>
```

This gets `--cc-surface-2` background from the global tonal card rule. No custom classes needed.

### Embedding the pipeline canvas in scoped mode (vision gates)

A vision-confirm gate is a callable rule authored in the **same** `PipelineCanvas`, not a second editor. To embed it:

- Pass the gate's rule id and `mode="gate"`: `<PipelineCanvas :rule-id="gateRuleId" mode="gate" />`. The default `mode="rule"`.
- The `mode` prop threads to `StepPalette`. Palette filtering is **metadata-driven**, never a hardcoded list: in `gate` mode it shows only steps with `gate_safe` (and includes `gate_only` steps like `gate_verdict`); in `rule` mode it hides `gate_only` steps. The flags come from `GET /pipeline/step-types` (`gate_safe`/`gate_only` on each step). Drive any new mode behaviour off those flags.
- In `gate` mode the canvas exposes a **Validate** action that calls `POST /api/v1/gate-graphs/{id}/validate` (full `validate_gate_graph`) and surfaces "exactly one reachable `gate_verdict`" + "all steps gate-safe" inline. Edge saves still go through the existing `PUT /rules/{id}/edges` (gate-safe structural check at edit time).
- Host the canvas inside `GateEditorDialog` (an `AppDialog size="xl"`). Add a preview/test-run button that calls `POST /api/v1/gate-graphs/{id}/test-run` and renders the `GateVerdict` (complete/confidence/reason + cost). See the AppDialog standard above.
- New step config components register in `frontend/src/components/pipeline/steps/index.js` and `stepMeta.js` (label/icon/dot color). Reuse the condition expression widget (`_shared/TemplateInput.vue`) for any expression field (`gate_verdict.complete_if`); do not build a new expression editor.
- Region editing (rects over a reference frame) is shared via `_shared/ImageCropCanvas.vue` and the shared region-list logic (`_shared/useRegionList.js`); step config components consume it and never reimplement region math. Step config components must render in both `StepConfigDialog` and the scoped gate canvas when their step is `gate_safe`.

### Right-side drawer pattern

Right-side drawers overlay the main content as full-viewport panels. The `.cc-drawer-right` class is a **global utility in `theme.css`**; do not add scoped CSS for it in individual views.

#### Width standards

Two widths only:

| Token | Value | Use |
|---|---|---|
| **Standard** | `width="480"` | Inspector panels, evidence, detail views, forms |
| **Wide** | `width="640"` | Complex multi-section views with maps, timelines, or side-by-side content |

Never use ad-hoc widths like 500 or 440. Pick the closest standard.

#### Template

```html
<v-navigation-drawer v-model="open" location="right" temporary width="480" class="cc-drawer-right">
  <!-- Plain div root: v-navigation-drawer provides the glass surface.
       Never use v-card flat; it inherits the global glass-border rule. -->
  <div class="h-100 d-flex flex-column">

    <!-- Fixed header: always rendered, contains title + close button -->
    <div class="d-flex align-center px-4 py-3">
      <span class="text-subtitle-1 font-weight-semibold">Panel Title</span>
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
    </div>

    <!-- Optional: status alerts, metadata chips (fixed height) -->
    <div v-if="alertCondition" class="px-4 pb-2">
      <v-alert type="warning" density="compact" variant="tonal">...</v-alert>
    </div>

    <!-- Optional: tabs (fixed height, followed by divider) -->
    <v-tabs v-model="tab" color="primary" density="compact" class="px-4">
      <v-tab value="summary">Summary</v-tab>
      <v-tab value="history">History</v-tab>
    </v-tabs>
    <v-divider />

    <!-- Scrollable body: must have min-height: 0 inside a flex column -->
    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <div class="pa-4">
        <!-- content -->
      </div>
    </div>
  </div>

  <!-- Confirmation dialogs: outside the inner div, inside the drawer.
       Always persistent; backdrop close leaves useConfirm's Promise hanging. -->
  <v-dialog v-model="confirmDialog" max-width="400" persistent>
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

#### No scoped CSS required

`.cc-drawer-right` is a global utility in `theme.css`. It sets:
- `position: fixed; top: 0; bottom: 0; height: auto`: full-viewport pinning
- `z-index: 2100`: above `v-app-bar` (approximately 1004) and VOverlay default (approximately 2000)
- `padding-top: 0`: correct; the drawer overlays the navbar (not behind it)
- `border-left` and a left-side shadow: creates visual separation from page content

Do not copy-paste these rules into a scoped `<style>` block. If a one-off override is needed, add a modifier class.

#### Transparency and surface

Drawers use `--cc-drawer-glass`, a solid surface in the single `ccWarm` theme (Marauders overrides it in `marauders.css`). Never add transparency; page content must not bleed through a drawer.

#### Rules

- **Width**: `480` (standard) or `640` (wide) only; no ad-hoc values
- **Root element**: plain `<div>`, never `v-card flat` (inherits unwanted glass border)
- **Header**: plain `<div class="d-flex align-center px-4 py-3">`, not `v-card-title`
- **Scrollable body**: `flex-grow-1 overflow-y-auto` with `style="min-height: 0"`
- **Confirm dialogs**: always `persistent` to prevent Promise from hanging
- **No scoped `.cc-drawer-right` CSS**: it is global in `theme.css`

## Data tables and pagination

### Table visual wrapper (mandatory)

Every `v-data-table` must be wrapped in `<v-card class="glass-card">`. This gives the table the warm-paper card surface, border, and shadow consistent with all other cards in the app.

```html
<v-card class="glass-card">
  <v-data-table :headers="headers" :items="items" :loading="loading" item-value="id">
    <!-- column templates -->
  </v-data-table>
</v-card>
```

For tables that are tool/workbench views (not CRUD list views), `density="compact" hide-default-footer :items-per-page="-1"` is acceptable when the dataset is small and pagination is unnecessary. These tables still use the `glass-card` wrapper.

### Server-side pagination (mandatory for all list views)

Every list view's `v-data-table` uses server-side pagination; the only exception is a small tool/workbench table, as stated above. The pattern:

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
- Identity/track columns should combine a human label with a short stable ID in a secondary line. Do not expose only a raw UUID when the user must compare or merge tracks.

### Bulk table actions

Bulk actions belong in the table toolbar and operate on `v-data-table-server` selected item IDs. The flow is:

1. Selection count chip.
2. One explicit action button per supported bulk operation.
3. A persistent review dialog when the operation needs additional choices, such as the merge target.
4. `useConfirm()` immediately before the API mutation.
5. One BFF batch endpoint for the mutation. Do not loop over single-row endpoints in the browser for merge/delete/correct operations; partial success is hard for caregivers to reason about and hard to recover from.

Bulk merge dialogs must show each candidate with display name, short PH ID, room/camera context, and last-seen time. The user chooses the target track to keep; all other selected PHs become sources.

### Annotation editor reuse

Keyframe thumbnails that open an editable image must use `components/cts/keyframes/KeyframeAnnotationDialog.vue`. Do not create custom image lightboxes for annotation-capable keyframes. The dialog already owns the standard header, bbox canvas, confidence filter, pending-change summary, save/cancel actions, and backend bbox batch contract.

When a PH keyframe thumbnail is clicked, pass the real `keyframe_id` and unmodified image URL to `KeyframeAnnotationDialog`; thumbnail privacy/blur rendering stays in the thumbnail component.

**Bounding-box interaction geometry is shared.** Both the keyframe annotation canvas (`BboxCanvas.vue`) and the pipeline crop-region canvas (`steps/_shared/ImageCropCanvas.vue`) draw/move/resize boxes using the pure helpers in `composables/bboxGeometry.js` (`hitTestRect`, `applyCornerDrag`, `normalizeRect`, `clamp01`; compass corner names `nw/ne/se/sw`). When building another box editor, reuse these rather than re-deriving corner hit-testing; keep rendering and coordinate-model (pixel vs ratio) per-component. Two non-negotiables for any such canvas: a **bare click must not create a box** (require a minimum drag, like `MIN_DRAW_PX`), or you persist degenerate 0-size regions; and selection/brand colors come from `ccToken('--cc-brand')` etc. (theme-adaptive incl. ccMarauders), while white-on-photo strokes are the intentional, theme-agnostic contrast convention over camera images, not a token gap.

**Box-canvas rendering model + Marauder's ink.** Both bbox canvases use the same three-layer model: an `<img>` for the frame, an absolute transparent `<canvas>` overlay for interaction/selection, and (gated by `useMaraudersMode().state.enabled`) an absolute `<svg viewBox="0 0 naturalW naturalH">` overlay (`pointer-events: none`) rendering committed boxes as `MaraudersInkBox` (seeded/memoized via `useRoughSketch`). Two rules make the ink behave: render the **committed** boxes as ink but **exclude the actively-dragged box** (draw it plain on the canvas during the gesture) so rough.js does not reseed every frame and shimmer (per the rough.js section below); and seed each `MaraudersInkBox` from a stable id (`region.id`), never the array index alone. Ink boxes are static art, so they need no reduced-motion fallback.

### Compact option selectors in page headers and table toolbars

**Do not use `v-btn-toggle`** for period/mode/source pickers in headers and toolbars. Vuetify's `v-btn-group` collapses the border between adjacent buttons (`border-inline-end: none`), making them visually merge into a single block. Spacing utility classes (`px-4`, `ga-*`) cannot fix this because they operate on padding/gap, not on the shared-border collapse.

**Use `CcSegmentedToggle`** (`components/common/CcSegmentedToggle.vue`). It encapsulates the DS segmented-picker pattern (individual `v-btn` in a `d-flex ga-2` row, active = `flat` + color, inactive = `outlined`), so you never re-implement it inline:

```html
<CcSegmentedToggle v-model="period" :options="PERIOD_OPTIONS" />
```

```js
const PERIOD_OPTIONS = [
  { value: "last_15m", label: "15m" },
  { value: "last_1h",  label: "1h"  },
  { value: "last_24h", label: "24h" },
  { value: "last_30d", label: "30d" },
];
```

- Options are `{ value, label, icon? }`. Props: `v-model`, `:options` (required), `size` (default `small`; use `default` to match comfortable-density rows), `color` (default `primary`).
- It is mandatory by nature (clicking selects; no toggle-off) and emits `update:modelValue`, so `v-model` plus a side-effecting `@update:model-value` handler both work.
- **Exception: a full-width, icon-only segmented control where merged segments are the intended affordance** (e.g. a text-alignment left/center/right control, like a word processor) may keep `v-btn-toggle variant="outlined"`. That is a different widget from a mode/period picker; `CcSegmentedToggle` is for the gapped-pill picker case. Reference: `components/eink/RegionEditor.vue`.

### Empty-state (`#no-data`) template

Every `v-data-table` must include a `#no-data` slot with a consistent empty-state message:

```html
<template #no-data>
  <div class="pa-6 text-center">
    <v-card flat>
      <v-card-text class="text-medium-emphasis text-h6">No X yet</v-card-text>
      <v-card-text class="text-medium-emphasis">
        Brief sentence about when data will appear.
      </v-card-text>
    </v-card>
  </div>
</template>
```

- Always use `#no-data`, never `#bottom` for empty-state messages (`#bottom` overrides the pagination footer)
- The text should be descriptive and reassuring
- The `v-card flat` keeps it visually subtle
- Use `text-medium-emphasis` for both lines (never a material color class such as `text-grey`)

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

## Form patterns

- All form fields inherit `variant="outlined"` and `density="comfortable"` from Vuetify defaults. Don't override unless you have a specific reason.
- **Labels sit above the field automatically** (global CSS -- see "What the global stylesheet handles"). Just pass the `label` prop normally; do not build your own stacked-label markup. Empty fields show an empty box under the label; add a `placeholder` if you want in-field hint text.
- For a genuinely inline/compact field where a label-above would break the row (e.g. a search box in a toolbar), omit `label` and use `placeholder` (and `density="compact" hide-details`) so the field stays label-less and inline.
- Putting a labeled field on the same row as a switch/checkbox/pill/button? Just make the row `align-items: center` (`d-flex align-center`, or `align="center"` on a `v-row`). The field box is vertically centered for you, so the control lines up with it automatically -- no extra class. Avoid a bare `d-flex` / `align="start"` here (the control would jump to the top of the row).
- In compact areas (question editors, expanded rows), use `density="compact" hide-details`.
- `v-switch`, `v-checkbox`, and `v-radio-group` are sage-when-on by default (DS) -- do not set `color="primary"` on them; it is already the global default.
- Use `:rules` on required fields: `[r => !!r || 'Field is required']`
- Always use `:loading` on submit buttons.
- Form state resets go in `closeCreateDialog()`: reset every field back to default.

## DS signature components (`components/common/`)

These reusable components implement design-system primitives. Prefer them over hand-rolled markup.

### `CcSegmentedToggle` -- segmented single-select picker

The DS replacement for `v-btn-toggle` in period/mode/source pickers. See "Compact option selectors" above for usage and the one icon-only full-width exception.

```html
<CcSegmentedToggle v-model="viewMode" :options="VIEW_MODE_OPTIONS" />
```

### `CcStatusPill` -- the wellbeing indicator

The signature DS status reading: a calm pill pairing a colored dot with a label and optional detail line. Use it for the headline wellbeing state of a person or room. Lead with the calm reading; only escalate `status` when something genuinely warrants attention.

```html
<CcStatusPill status="steady" detail="Calm night, up at 7:10am" />
<CcStatusPill status="notice" label="Worth a look" detail="Quieter in the kitchen" />
```

Statuses: `steady` | `notice` | `quiet` | `alert`. This is distinct from a status `v-chip` (which uses the per-view `statusColor()` helper for table cells) -- use `CcStatusPill` for the prominent, human-facing reading and `v-chip` for compact table status.

### `CcAvatar` -- person likeness

Shows a photo when available, otherwise warm initials on a calm color derived from the name, with an optional wellbeing ring. Use it for people (the senior, caregivers) -- not for decorative icon containers, which stay as plain `v-avatar`.

```html
<CcAvatar name="Ruth Alvarez" size="lg" status="steady" />
<CcAvatar name="Dana" :src="photoUrl" />
```

Sizes: `xs | sm | md | lg | xl`. `status` (optional): `steady` | `notice` | `alert`.

## Right-hand inspector drawer with deep enrichment

This pattern applies to any drawer that shows detail for a selected list row and loads additional data sections lazily (observations, trail, revisions, co-present entities). Reference implementation: `PHInspectorDrawer.vue`.

### Structure rules

1. **The drawer component is a thin coordinator.** It receives the selected item as a prop, delegates all data fetching to a `useDetail` composable, and delegates all mutation to a `useCorrection` composable. It never contains inline fetch logic.

2. **Tabs split heavy sections.** Use `v-tabs` + `v-window` inside the drawer to split: Summary (always visible), Evidence/Observations (lazy), History/Revisions (lazy), Actions. This prevents loading all sections on every row click.

3. **Six-component decomposition.** For any inspector with 4+ distinct data sections, extract each section into its own component. The naming convention is `{Domain}{Section}.vue`. Example (`components/cts/ph/`): `PHObservationsTimeline.vue`, `PHRevisionsFeed.vue`, `PHTrailMiniFloorPlan.vue`, `PHLifecycleActions.vue`, `PHPosteriorPanel.vue`, `PHKeyframeStrip.vue`, `PHListPanel.vue`. Do not inline these sections in the drawer.

4. **Confirmation on all destructive actions.** Any action that is hard to reverse (merge, split, delete, reassign) must call `useConfirm()` before proceeding. Never allow an irreversible action without a dialog confirmation.

5. **`useNotify()` for all outcomes.** Success, warning, and error states surface via `useNotify()`, not `console.log` or native `alert()`.

6. **Row click wires `@click:row`, not just a button.** On `v-data-table-server`, add both:
   - `@click:row="(_event, { item }) => openDrawer(item)"` for the full-row click
   - `hover` prop to show pointer cursor
   - A dedicated Inspect button inside `#item.actions` that calls `event.stopPropagation(); openDrawer(item)` to avoid double-open

7. **All time in the drawer uses `services/timezone.js`.** Never `new Date().toLocaleString()` or raw `Date` methods.

### Template skeleton

```html
<v-navigation-drawer v-model="open" location="right" temporary width="480" class="cc-drawer-right">
  <!-- Plain div root; do NOT use v-card flat (gets unwanted glass border from theme.css) -->
  <div class="h-100 d-flex flex-column">
    <!-- Fixed header -->
    <div class="d-flex align-center px-4 py-3">
      <PHListPanel :item="selectedItem" />
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
    </div>

    <!-- Optional alert banner -->
    <div v-if="state.error" class="px-4 pb-0">
      <v-alert type="error" density="compact">{{ state.error }}</v-alert>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="tab" color="primary" density="compact" class="px-4">
      <v-tab value="summary">Summary</v-tab>
      <v-tab value="observations">Observations</v-tab>
      <v-tab value="history">History</v-tab>
      <v-tab value="actions">Actions</v-tab>
    </v-tabs>
    <v-divider />

    <!-- Scrollable body -->
    <div class="flex-grow-1 overflow-y-auto" style="min-height: 0">
      <div class="pa-4">
        <v-window v-model="tab">
          <v-window-item value="summary">
            <PHTrailMiniFloorPlan :trail-points="state.trail" />
            <PHPosteriorPanel :item-id="selectedItem.id" />
          </v-window-item>
          <v-window-item value="observations">
            <PHObservationsTimeline :item-id="selectedItem.id" />
          </v-window-item>
          <v-window-item value="history">
            <PHRevisionsFeed :item-id="selectedItem.id" />
          </v-window-item>
          <v-window-item value="actions">
            <PHLifecycleActions :item-id="selectedItem.id" @corrected="onCorrected" />
          </v-window-item>
        </v-window>
      </div>
    </div>
  </div>

  <!-- Confirmation dialogs outside the inner div but inside the drawer.
       Always use persistent: backdrop click otherwise leaves the Promise hanging. -->
  <v-dialog v-model="confirmDialog" max-width="400" persistent>
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

No scoped CSS needed; `.cc-drawer-right` is a global utility in `theme.css`.

## Tracking workspace and pipeline canvas

### Pipeline builder canvas (editor)

The editor canvas (`PipelineCanvas.vue`) uses VueFlow; the read-only monitor canvas (`PipelineMonitorCanvas.vue`) shares `edgesToVueFlow` from `useCanvasPipeline.js`.

- **Editing is controlled.** `state.edges` (in `useCanvasPipeline`) is the source of truth and is reloaded from the backend after every mutation. Do not mutate VueFlow's internal store. Connecting fires `@connect` -> `actions.addEdge`; deleting fires `@edges-change` (type `remove`) -> `actions.removeEdge`. Both persist via `api.replaceRuleEdges`, which sends the full edge set.
- **Edge deletion** uses `edges/DeletableEdge.vue` (a custom edge: `BaseEdge` + `EdgeLabelRenderer`), wired only on the editor via `:edge-types` + an `editorEdges` computed that overrides the type to `deletable` (the shared `edgesToVueFlow` stays type-neutral so the monitor keeps plain `smoothstep`). The delete button calls `useVueFlow().removeEdges([id])` -> the same `@edges-change` path. Note: `EdgeLabelRenderer` **teleports** the button out of the edge's SVG group, so a `:deep(.vue-flow__edge:hover) ...` descendant selector cannot reveal it; keep the affordance visible (or drive it from the `selected` prop), don't rely on edge-hover.
- **Fan-out is allowed.** One source handle can have many edges. `validateConnection` rejects only: self-loops, a target port other than `main`, an undeclared source port, and an *exact-duplicate* edge (same source+port+target). Never reject "this output port is already connected", and use length checks (not `?? []`) when reading a node's `outputPorts` so an empty array doesn't silently reject every connection.
- **Image-source step configs** use the shared `components/pipeline/steps/_shared/ImageSourceSelector.vue` (the source `<v-select>` plus per-source sub-config: trigger count, reCamera `CameraSelector`, time filter, pipeline path, cts_window path; step-specific extras go through its default slot). It is adopted by `image_crop`, `llm_call`, `scene_analysis`, and `person_identification`; do not re-paste the source select per config. `StepConfigDialog` fetches the CTS roster via `cts.getCameras()` and threads `ctsCameraItems` (CTS) alongside `cameraSensorItems` (reCamera) to the configs.


### Tracking workspace information architecture

The `TrackingWorkspace.vue` view is the single role-aware tracking dashboard. It uses `usePersonPresence` as the one composable for all person-location data (design rule D1). Rules:

- Do not create a second composable that fetches person location data.
- Panel visibility is currently controlled by the `role` prop and `ROLE_CONFIG` in `frontend/src/views/tracking/TrackingWorkspace.vue`. Treat this as the permission boundary until a shared authorization store replaces it; do not hardcode role checks inside individual panels.
- Add new panels as children of `TrackingWorkspace`, not as new top-level views.


### Tracking panel-addition checklist

1. Create the panel under `frontend/src/views/tracking/panels/` and use `TrackingPanelHeader` for its title, description, and actions.
2. Add one entry to `ALL_TABS`, one `v-window-item`, and the intended role visibility in `ROLE_CONFIG`.
3. Keep route query behavior working: an unauthorized or unknown `?panel=` value must resolve to that role's default panel.
4. Reuse the owning composable for existing data. Person-location panels consume the single `usePersonPresence` instance created by `TrackingWorkspace`; a new data domain gets one `{ state, actions }` composable such as `useGaitTrend`.
5. Pass shared workspace data to presentational panels through props. Do not add a fallback API call inside a panel.
6. Reuse shared chart and dashboard components from the data-visualization skill and render loading, error, and empty states.
7. Extend `frontend/tests/views/tracking/TrackingWorkspace.test.js` for tab visibility/default routing and add a panel test that proves rendering plus data ownership.


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

---

## Adding a new admin list view

For CTS identity keyframes, Person Hypothesis corrections, provenance badges, or ReID review
surfaces, also load
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/cts-identity-admin/SKILL.md`.

1. Create `frontend/src/views/admin/NewResourceView.vue`
2. Follow the page layout pattern (header row + glass-card + table + dialogs)
3. Add API methods to the matching module in `services/modules/` (create one if the domain is
   new); they are typed against the generated `paths`, and `api.js` needs no edit
4. If the endpoint is new, run `make openapi` and `npm run generate:api`, and commit both
5. Wire the route in the router config
6. Add to the admin nav drawer in `AdminView.vue`
7. Add `auth.yaml` entries for each new endpoint
8. Ensure server-side pagination with `:items-length` + `:page` + `@update:options`

## Admin dashboard cards

`CcDailyLivingHealthCard.vue` (`components/dashboard/`) is the reference
implementation for an admin health/telemetry card. New admin cards mirror this
structure rather than forking it:

1. **Data via a generated-client composable.** A `use<Name>.js` composable under
   `composables/` wraps a typed function from `services/modules/<domain>.ts` (built on the
   generated OpenAPI client) and returns `{ state: { loading, error, ...data }, actions:
   { refresh, ... } }`. Polling, if the surface needs it, is caller-driven (the mounting view
   starts/stops a timer that calls `actions.refresh`); the composable itself never hides a
   timer.
2. **Charts via the shared `Cc*` chart components**, themed with `useChartTheme` (see the
   data-visualisation skill's form heuristic for which chart shape fits the data).
3. **Stale/alert states use the existing design-system warning treatment**: the
   `status` prop on `CcMetricTile` (`'ok' | 'warning' | 'error' | 'info'`, mapped to Vuetify's
   `success`/`warning`/`error`/`info` colors and matching icons) for tile-level state, and a
   `v-alert type="warning" variant="tonal"` banner for a section-level stale/degraded call-out.
   Never invent a bespoke color or icon set for "this data is old" or "this data is missing".
4. **Card body lives in `components/dashboard/`, wrapped in `CcSectionCard`** for the
   title/subtitle/actions-slot chrome; the card mounts into the owning admin view (today,
   `DashboardView.vue`) rather than becoming its own routed view, unless the data volume
   genuinely warrants a dedicated page.
5. **Timestamps always go through `services/timezone.js`** (`formatRelative` from
   `composables/useFormatRelative.js` for "N minutes ago" style ages, `formatDateTimeShort`/
   `formatDateTime` for absolute stamps). Never `toLocaleString()` or hand-rolled relative-time
   math.

The inference-load telemetry card follows this same pattern.

## Routine Builder

The guided-task Routine Builder is a linear step-list editor, not a Vue Flow
graph canvas. Reuse the existing SchemaForm and step-config components where they
fit, and expose per-routine policy overrides, per-step policy overrides,
completion-gate settings, and zone/camera pickers without introducing a parallel
pipeline-authoring model.

Use the guided-companion skill for the routine/session data model and domain rules:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/guided-companion/SKILL.md`.
