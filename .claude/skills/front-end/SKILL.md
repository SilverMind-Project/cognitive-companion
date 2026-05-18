# Frontend Engineering Skill

Guidelines for building and modifying the Cognitive Companion Vue 3 + Vuetify frontend. Every agent working on this codebase must follow these patterns.

---

## Styling system

### Design tokens (`frontend/src/styles/theme.css`)

All custom CSS properties are prefixed `--cc-` and live in three blocks:

- `:root` — brand colors, geometry radii, typography stacks (shared across themes)
- `.v-theme--ccDark` — dark-mode surface, text, border, shadow values
- `.v-theme--ccLight` — light-mode overrides for the same tokens

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
- `v-app-bar`, `v-navigation-drawer` — `backdrop-filter: saturate(200%) blur(20px)`
- All elevated `v-card` (non-outlined, non-tonal) — glass surface + border + shadow
- Dialog cards (`v-dialog > .v-overlay__content > .v-card`) — `--cc-bg-elevated` + 28px blur + stronger border
- Input fields (`v-field--variant-outlined`) — `--cc-surface-3` + 6px blur

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

**Do NOT use `#bottom` template** for "No items yet" messages. When `totalItems` is 0, Vuetify shows its built-in empty state. Use `#no-data` for custom empty-state content — it renders only when there is zero data and loading is complete, without overriding the pagination footer.

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
- Form state resets go in `closeCreateDialog()` — reset every field back to default.

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

## Common mistakes to avoid

1. **Hardcoded `rgba(255, 255, 255, …)` colors** — these break in light mode. Use `--cc-*` variables or Vuetify named colors.
2. **Scoped `<style>` blocks with custom colors** — use global utility classes and Vuetify variants instead.
3. **Static `:items-per-page`** on data tables — use server-side pagination with `:items-length`.
4. **Not resetting `page = 1` on filter changes** — causes empty pages when filters narrow results.
5. **`item-title="title"` on layout selects** — layout objects use `display_name`, not `title`.
6. **Sending fields not in the backend schema** — check the Pydantic model for allowed fields (many schemas use `extra="forbid"`).
7. **`toLocaleString()` for dates** — use `formatDateTime` from `@/services/timezone.js`.
8. **`alert()` / `confirm()` in Vue** — use `useNotify()` / `useConfirm()`.
9. **Extra fields in PATCH requests** — PATCH schemas have `extra="forbid"`. Only send fields defined in the Update schema.
10. **Margin classes on Vuetify wrapper components inside slot templates** — `v-chip`, `v-btn`, and `v-avatar` render internal DOM wrappers that can absorb `mr-2`/`ml-2` classes, making the margin invisible. Always wrap these components in a `<div>` with the margin class when they appear in `#prepend` or `#append` slots:

    ```html
    <!-- WRONG — margin may land on an internal wrapper -->
    <template #prepend>
      <v-chip class="mr-2">Label</v-chip>
    </template>

    <!-- RIGHT — margin on a plain div is always visible -->
    <template #prepend>
      <div class="mr-2">
        <v-chip>Label</v-chip>
      </div>
    </template>
    ```

    Simple elements (`v-icon`, `<span>`) do not have this issue and can take margin classes directly. In `#prepend` slots, use `mr-2` (push content right); in `#append` slots, use `ml-2` (push content left).

---

## File organization

```
frontend/src/
  styles/theme.css          — global design tokens + Vuetify overrides
  services/api.js           — all API calls
  services/contracts.js     — response shape validation
  services/timezone.js      — datetime formatting + constants
  composables/useNotify.js  — snackbar notifications
  composables/useConfirm.js — promise-based confirmation dialog
  components/common/        — reusable shared components (LlmModelPicker, etc.)
  components/pipeline/      — rule pipeline builder components
  components/companion/     — senior-facing companion UI
  views/admin/              — admin dashboard views (one per resource)
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
