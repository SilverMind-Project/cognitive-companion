---
name: front-end
description: "Use when changing Cognitive Companion Vue, Vuetify, routing, Tracking workspace panels, composables, layouts, drawers, dialogs, styling, or frontend tests."
---

# Frontend Engineering Skill

Guidelines for building and modifying the Cognitive Companion Vue 3 + Vuetify frontend. Every agent working on this codebase must follow these patterns.

---

## Styling system

This app uses **Cognitive Companion Design System v2**: warm editorial calm. Warm cream paper background, grounded sage green primary, terracotta accent, deep warm ink text. No frosted glass, no blue/purple tech palette, no animated gradients. Calm motion. Senior-legible type.

### Brand in one sentence

Three feelings: **calm**, **dignity**, **trust**. Surfaces are warm paper. Type is humanist serif (headings) + humanist sans (body) + monospace (data). Semantic colors are muted, never alarming.

### Fonts

| Token | Face | Role |
|---|---|---|
| `--cc-font` | Hanken Grotesk | All UI body text, labels, buttons |
| `--cc-font-display` | Newsreader | Page headings, card titles, brand name, tender moments |
| `--cc-font-mono` | IBM Plex Mono | Timestamps, IDs, data values |

Vuetify's `$body-font-family` maps to `--cc-font`, `$heading-font-family` maps to `--cc-font-display`. Don't override these per-component.

### Design tokens (`frontend/src/styles/theme.css`)

All custom CSS properties are prefixed `--cc-` and live in two blocks:

- `:root`: DS v2 primitive scales (stone/sage/terra), invariant spatial tokens, fonts, radii
- `.v-theme--ccWarm`: all surface, text, border, shadow, and brand tokens for the single warm theme

Marauders parchment tokens live in `marauders.css` only (overrides a subset of `--cc-*` on `.v-theme--ccMarauders`). Never add per-theme rules to component scoped styles.

**Always use these variables** instead of hardcoded colors:

```css
/* Surfaces */
--cc-bg               /* #FBF8F3 warm cream page background */
--cc-bg-elevated      /* #FFFDF9 dialog / elevated card */
--cc-surface          /* #FFFDF9 card surface */
--cc-surface-2        /* #F4EDE2 tonal / table header / inset section */
--cc-surface-3        /* #F4EDE2 input field background */

/* Text */
--cc-text-1           /* #1D1A14 primary -- warm near-black */
--cc-text-2           /* #5F5544 secondary / medium-emphasis */
--cc-text-3           /* #877960 tertiary / disabled / section headers */

/* Brand */
--cc-brand            /* #3F6B52 sage-500 -- primary action color */
--cc-brand-strong     /* #305340 sage-600 -- hover state */
--cc-brand-soft       /* rgba(63,107,82,0.12) -- tonal chip / highlight */
--cc-brand-softer     /* rgba(63,107,82,0.06) -- active nav item tint */

/* Semantic */
--cc-success          /* #2F8F5B green-care */
--cc-warning          /* #C98A2E gold-notice */
--cc-error            /* #BC5740 brick-alert (muted, never alarm-red) */
--cc-info             /* #4E7A8C blue-info */

/* Borders */
--cc-divider          /* #E8DDCC hairline warm neutral */
--cc-divider-strong   /* #D6C7AF slightly stronger */
--cc-glass-border     /* #E8DDCC card border (same as divider) */
--cc-glass-border-strong /* #D6C7AF dialog border */

/* Shadows -- warm ink, soft daylight */
--cc-shadow-xs / --cc-shadow-sm / --cc-shadow-md / --cc-shadow-lg
--cc-shadow-glass     /* same as --cc-shadow-sm */
--cc-shadow-glass-hover /* same as --cc-shadow-md */
--cc-shadow-inset     /* inset 0 1px 2px -- soft depth for input fields */

/* Focus -- DS signature terracotta ring */
--cc-focus-ring       /* terra-300 #DC8D6B */
--cc-shadow-focus     /* 0 0 0 3px var(--cc-focus-ring) -- keyboard focus ring */

/* Radii */
--cc-radius-xs: 6px; --cc-radius-sm: 10px; --cc-radius-md: 14px;
--cc-radius-lg: 20px; --cc-radius-xl: 28px; --cc-radius-pill: 999px;
```

### What the global stylesheet handles automatically

The global `theme.css` rules apply to the Vuetify components below. **Never add a background-color, border, or shadow to these elements directly** -- the global rules own them and your inline styles will conflict or break on theme switch to ccMarauders.

- `v-app-bar`: `--cc-app-bar-glass` background, `--cc-divider` bottom border
- `v-navigation-drawer`: `--cc-drawer-glass` background, `--cc-divider` border
- Elevated `v-card` (non-outlined, non-tonal, non-flat): `--cc-surface` background, `--cc-glass-border` border, `--cc-shadow-glass` shadow, `--cc-radius-lg` (20px) corners. Overlay cards inside `.v-overlay__content` (menus) stay tight at `--cc-radius-sm`.
- `v-card.v-card--variant-tonal`: `--cc-surface-2` background
- Dialog cards: `--cc-bg-elevated` background, `--cc-shadow-lg`, `--cc-radius-xl` (28px)
- `v-field--variant-outlined` inputs: `--cc-surface` background, `--cc-radius-md` corners, soft `--cc-shadow-inset`, `--cc-divider-strong` border; on focus a sage border plus a soft terracotta `--cc-shadow-focus` ring
- **Outlined field labels render ABOVE the field, not floating in the border (DS Input/Select).** The global rule moves the `label` out of Vuetify's notch to a static line above the field, keeps the top border solid (no notch cut), and fixes the field box at 48px. Any field with a `label` (any density) gets a 24px label band reserved as **`padding-top`** on the input wrapper -- real height that never collapses with the previous field's margin, so the label can't be clipped by the field on the line above. Hint/error stay below. Do not fight this with per-field CSS or floating-label hacks.
- Field background: enabled `--cc-surface` (DS surface-card #FFFDF9, solid -- no gradient); disabled `--cc-surface-2` (DS surface-sunk).
- **The field box stays vertically centered in the input.** A `hide-details` labeled field has no bottom slot to balance the top label band, so the global rule mirrors the band (`--cc-field-label-band`) as `padding-bottom` on it. This keeps the box centered, which means buttons/toggles/checkboxes placed next to a field in an `align-items: center` row line up with the field box **automatically** -- no per-row class. (Fields that show a hint/error already have a balancing bottom slot and are excluded.)
- **Invariant for mixed rows:** a row that puts a labeled field next to a switch/checkbox/pill/button MUST use `align-items: center` (the standard header pattern `d-flex align-center` already does; for a `v-row`/`v-col` grid use `align="center"`). That is what keeps the control aligned with the field box. A bare `d-flex` (defaults to `stretch`) or `align="start"` will drop the control to the top -- add `align-center`.
- Focus (keyboard): `.v-btn`, links, and `[tabindex]` elements get the terracotta `--cc-shadow-focus` ring via `:focus-visible`. Do not add custom focus outlines.

### Utility classes (defined in `theme.css`)

| Class | Use |
|---|---|
| `.glass-card` | Warm paper card with hairline border and hover lift. Use on non-Vuetify wrappers and explicit card wrappers. |
| `.cc-card-soft` | DS Card "soft" tone -- sage-tinted panel for gentle emphasis. Add alongside a card class. |
| `.cc-card-accent` | DS Card "accent" tone -- terracotta-tinted panel for warm, human moments. Add alongside a card class. |
| `.cc-badge` + `.cc-badge--{good,notice,alert,info,brand}` | DS Badge: calm pill status label with hand-tuned tone pairs. Add `<span class="cc-badge__dot" />` inside for the leading dot. For one-off status labels; existing semantic `v-chip`s keep their `statusColor()` mapping. |
| `.stat-card` | Dashboard metric panel. Hover lift + sage border accent. |
| `.cc-inset-section` | Grouped sub-section within dialogs. Uses `--cc-surface-2`. |
| `.cc-gradient-text` | Newsreader brand text in sage. Used for the app name in the nav. |
| `.cc-eyebrow` | Small-caps tracked label in terracotta (`--terra-500`) -- the warm spark accent. Use above section titles. |
| `.cc-code` | Inline monospace code chip in sage tint. |
| `.cc-main-container` | `max-width: 1440px` centered container. |
| `.tracking-tight` | `letter-spacing: -0.014em`. Use on all page titles (`text-h4`). |

### Vuetify theme

There is a single product theme: `ccWarm`. The Marauders Easter-egg uses `ccMarauders` (separate parchment palette in `marauders.css`).

- The `defaultTheme` in `main.js` is `ccWarm` (unless localStorage says `ccMarauders`).
- There is no dark mode toggle. Do not add a theme switcher for ccDark/ccLight -- those themes were removed.
- Vuetify `color="primary"` resolves to sage-500 (`#3F6B52`). `color="secondary"` resolves to terra-400 (`#C8704F`).
- `VSwitch`, `VCheckbox`, and `VRadioGroup` default to `color="primary"` in `main.js`, so selection controls read **sage when on** (never neutral grey). `VSwitch` also defaults to `inset`. Do not redundantly set `color="primary"` on these -- it is already the default.
- Chart palettes derive from `--cc-*` tokens via `useChartTheme()` -- charts adapt automatically.

### DS v2 color philosophy

- Page backgrounds are warm paper, never cold white or dark.
- Cards are off-white warm paper (`--cc-surface`), not translucent glass.
- Borders are hairline warm stone, not deep or glowing.
- Shadows are warm-ink-tinted (rgba(45,38,26,...)), not blue-tinted.
- The "notice" level (yellow/amber) is used for gentle attention; `--cc-error` (brick-alert) is used for things needing awareness, never alarm-red neon.
- Avoid blue. The closest blue in the palette is `--cc-info` (#4E7A8C), used for neutral informational contexts only.

---

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

Dialogs use a solid elevated surface (`--cc-bg-elevated`), not the translucent `--cc-surface` used by cards. Use plain `<v-card>` with no custom class:

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

A vision-confirm gate is a callable rule authored in the **same** `PipelineCanvas`, not a second editor. To embed it (VG08):

- Pass the gate's rule id and `mode="gate"`: `<PipelineCanvas :rule-id="gateRuleId" mode="gate" />`. The default `mode="rule"`.
- The `mode` prop threads to `StepPalette`. Palette filtering is **metadata-driven**, never a hardcoded list: in `gate` mode it shows only steps with `gate_safe` (and includes `gate_only` steps like `gate_verdict`); in `rule` mode it hides `gate_only` steps. The flags come from `GET /pipeline/step-types` (`gate_safe`/`gate_only` on each step). Drive any new mode behaviour off those flags.
- In `gate` mode the canvas exposes a **Validate** action that calls `POST /api/v1/gate-graphs/{id}/validate` (full `validate_gate_graph`) and surfaces "exactly one reachable `gate_verdict`" + "all steps gate-safe" inline. Edge saves still go through the existing `PUT /rules/{id}/edges` (gate-safe structural check at edit time).
- Host the canvas inside `GateEditorDialog` (an `AppDialog size="xl"`). Add a preview/test-run button that calls `POST /api/v1/gate-graphs/{id}/test-run` and renders the `GateVerdict` (complete/confidence/reason + cost). See the AppDialog standard above.
- New step config components register in `frontend/src/components/pipeline/steps/index.js` and `stepMeta.js` (label/icon/dot color). Reuse the condition expression widget (`_shared/TemplateInput.vue`) for any expression field (`gate_verdict.complete_if`); do not build a new expression editor.

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

Drawers use `--cc-drawer-glass` which is near-opaque by design:
- **Dark mode**: `rgba(18, 18, 22, 0.96)`, deep and essentially solid
- **Light mode**: `rgba(248, 248, 252, 0.97)`, near-white so page content does not bleed through

The backdrop-filter blur is kept for subtle depth even at high opacity. Never increase transparency; a translucent drawer is distracting, especially in light mode where the page background shows through.

#### Rules

- **Width**: `480` (standard) or `640` (wide) only; no ad-hoc values
- **Root element**: plain `<div>`, never `v-card flat` (inherits unwanted glass border)
- **Header**: plain `<div class="d-flex align-center px-4 py-3">`, not `v-card-title`
- **Scrollable body**: `flex-grow-1 overflow-y-auto` with `style="min-height: 0"`
- **Confirm dialogs**: always `persistent` to prevent Promise from hanging
- **No scoped `.cc-drawer-right` CSS**: it is global in `theme.css`

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
- **Labels sit above the field automatically** (global CSS -- see "What the global stylesheet handles"). Just pass the `label` prop normally; do not build your own stacked-label markup. Empty fields show an empty box under the label; add a `placeholder` if you want in-field hint text.
- For a genuinely inline/compact field where a label-above would break the row (e.g. a search box in a toolbar), omit `label` and use `placeholder` (and `density="compact" hide-details`) so the field stays label-less and inline.
- Putting a labeled field on the same row as a switch/checkbox/pill/button? Just make the row `align-items: center` (`d-flex align-center`, or `align="center"` on a `v-row`). The field box is vertically centered for you, so the control lines up with it automatically -- no extra class. Avoid a bare `d-flex` / `align="start"` here (the control would jump to the top of the row).
- In compact areas (question editors, expanded rows), use `density="compact" hide-details`.
- `v-switch`, `v-checkbox`, and `v-radio-group` are sage-when-on by default (DS) -- do not set `color="primary"` on them; it is already the global default.
- Use `:rules` on required fields: `[r => !!r || 'Field is required']`
- Always use `:loading` on submit buttons.
- Form state resets go in `closeCreateDialog()`: reset every field back to default.

---

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

### One endpoint owns each fact; no cross-contract fallbacks

Do not wrap a fetch in a `try/catch` whose fallback recovers the **same** fact from a **different** endpoint's envelope -- e.g. "if `getSampleImage()` fails, dig the URL out of `getMediaBuffer().items[0].images[0].url`". This couples the component to a contract shape it does not own. When the `media.buffer` envelope migrated from a raw array to `{items, total}`, this fallback in `ImageCropConfig` had to be hand-patched even though nothing about crop sampling changed -- a component dragged into every unrelated contract migration. The fallback's `catch {}` also swallows the real error. This is the consumer-side twin of the data-ownership rule below (single fetch owner): one source of truth per fact, on the producer side *and* the consumer side.

Fix order when you reach for such a fallback:
1. A dedicated endpoint usually already covers the case (here `/pipeline/image-sources/sample` already resolved both reCamera and CTS). Call it alone, `notify.error(...)` on failure, and delete the fallback.
2. Only if no endpoint covers the case, add coverage server-side. Never client-composite one fact out of an envelope that exists to serve a different fact.

Legitimate composition -- a view fetching two *distinct* facts from two endpoints -- is unaffected. The rule targets re-deriving one fact from a contract you do not own.

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

### Shared composables

| Composable | Use when |
|---|---|
| `useAggregatorState.js` | Polling and server-pagination state for unified reCamera/CTS buffer telemetry, including capped per-camera depth history |

### Shared composable contract discipline

- Treat a composable's returned keys as a public API. Return one canonical key
  per value; never expose the same ref, computed, object, or function under two
  names.
- A child component prop name does not dictate the composable key name. Bind the
  canonical value directly, for example
  `<v-chart :theme="chartTheme" />`.
- Before adding or renaming a composable return key, inspect the implementation,
  all production consumers, tests, and skill examples with `rg`.
- Test mocks must reproduce the real return contract exactly. Do not add a
  convenient field to a mock that the production composable does not return.
- For small stable composables, add a contract assertion for the returned key
  set. This catches accidental aliases and undocumented API growth.

---

## Testing and warning hygiene

The frontend test suite must be warning-clean. A passing test run with `stderr` warnings is not complete.

### Test file location

All frontend tests live under `frontend/tests/`. The directory structure mirrors `frontend/src/`:

| Source | Test |
|---|---|
| `src/composables/useFoo.js` | `tests/composables/useFoo.spec.js` |
| `src/views/admin/FooView.vue` | `tests/views/FooView.spec.js` |
| `src/components/cts/Foo.vue` | `tests/components/cts/Foo.test.js` |
| `src/router/index.js` | `tests/router/` |
| `src/services/api.js` (bundle check) | `tests/bundle.test.js` |

**Never place test files inside `frontend/src/`** (e.g. `src/composables/__tests__/`). Tests are not part of the application bundle and must stay in `frontend/tests/`.

Imports from test files use the `@/` alias to reference source modules:

```js
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";
import FooView from "@/views/admin/FooView.vue";
```

Do not use relative imports like `../src/composables/useFoo` from tests.

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

1. **Hardcoded hex colors or `rgba()` values in scoped styles**: always use `--cc-*` tokens. Hardcoded colors ignore the ccMarauders theme override and will look wrong in Marauders mode.
2. **Blue/purple colors that aren't in the DS**: no `#007aff`, no `#5e5ce6`, no purple. If you need a status color, use the DS semantic tokens (`--cc-success`, `--cc-warning`, `--cc-error`, `--cc-info`).
2a. **Vuetify material color names on `color=`**: never `color="green|orange|purple|deep-purple|blue|red"` on `v-icon`/`v-chip`/`v-btn` -- those are Vuetify's material palette, not the DS. Map to DS semantic theme colors: `green`->`success`, `orange`/`amber`->`warning`, `red`->`error`, `blue`/`deep-purple`->`info` (or `secondary` for a warm accent like a capability badge). For a neutral/muted chip, **remove** the `color` attr so `variant="tonal"` falls back to the warm `--cc-surface-2`; do not invent a `--cc-grey` token. For a muted icon use `color="var(--cc-text-3)"`.
2b. **Undefined `--cc-*` token names** silently fall back (to the fallback arg, or to an invalid value -> default). The real tokens: brand is `--cc-brand` (not `--cc-primary`); secondary/tertiary text is `--cc-text-2` / `--cc-text-3` (not `--cc-text-secondary`/`--cc-text-primary`). When in doubt, grep the name against `theme.css`. A quick audit: collect `var(--cc-*)` names used vs. the names defined in `theme.css`/`marauders.css` and diff -- any "used but not defined" is a bug (component-local CSS vars defined in the same scoped block are the only legitimate exception).
3. **Scoped `<style>` blocks with surface/text colors**: use global utility classes and Vuetify variants instead.
3. **Static `:items-per-page`** on data tables: use server-side pagination with `:items-length`.
4. **Not resetting `page = 1` on filter changes**: causes empty pages when filters narrow results.
5. **`item-title="title"` on layout selects**: layout objects use `display_name`, not `title`.
6. **Sending fields not in the backend schema**: check the Pydantic model for allowed fields (many schemas use `extra="forbid"`).
7. **`toLocaleString()` for dates**: use `formatDateTime` from `@/services/timezone.js`.
8. **`alert()` / `confirm()` in Vue**: use `useNotify()` / `useConfirm()`.
9. **Extra fields in PATCH requests**: PATCH schemas have `extra="forbid"`. Only send fields defined in the Update schema.
10. **Incomplete test harnesses**: unresolved Vuetify components, missing router injections, and Vue Router config warnings are defects. Mount with the right plugin or explicit stubs; never suppress the warning.
10a. **Data consts in a plain `<script>` block referenced from the template**: in an SFC that has *both* `<script>` and `<script setup>` (e.g. the pipeline step configs, which export `stepDefaults`/`stepTabs` from `<script>`), the template can resolve **component imports** from the plain `<script>` (shared module scope) but **not** plain data consts -- those resolve only from `<script setup>` bindings. A `const FOO = [...]` in `<script>` is `undefined` in the template (silent: it falls back to a prop default, no build error). Declare template-referenced data in `<script setup>` (it may still read an import from the plain `<script>`, since they share module scope). The build won't catch this; a mounted runtime check will.
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
12. **Cross-contract fallback fetch**: a `catch` that recovers the same value from a *different* endpoint's envelope (e.g. falling back to `getMediaBuffer()` when `getSampleImage()` fails). Couples you to a contract you don't own and swallows the error; call the dedicated endpoint alone and `notify.error` on failure. See "One endpoint owns each fact; no cross-contract fallbacks".

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

---

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

---

## Data visualisation

### Authorised libraries

- **`echarts` (v6) + `vue-echarts` (v8)**: the only permitted charting library. Use explicit module imports only; never import the full ECharts bundle.
- **`@vue-flow/core` (v1.x)**: the interactive workflow editor library. Used exclusively in the pipeline builder canvas (`PipelineCanvas.vue`) and its editor sub-components. Not permitted in monitoring views or dashboards. ECharts (`CcDagChart.vue`) remains the standard for read-only DAG monitoring.
- No second charting library. No hand-rolled SVG charts for data shapes covered by the shared components.

### Pipeline builder canvas (editor)

The editor canvas (`PipelineCanvas.vue`) uses VueFlow; the read-only monitor canvas (`PipelineMonitorCanvas.vue`) shares `edgesToVueFlow` from `useCanvasPipeline.js`.

- **Editing is controlled.** `state.edges` (in `useCanvasPipeline`) is the source of truth and is reloaded from the backend after every mutation. Do not mutate VueFlow's internal store. Connecting fires `@connect` -> `actions.addEdge`; deleting fires `@edges-change` (type `remove`) -> `actions.removeEdge`. Both persist via `api.replaceRuleEdges`, which sends the full edge set.
- **Edge deletion** uses `edges/DeletableEdge.vue` (a custom edge: `BaseEdge` + `EdgeLabelRenderer`), wired only on the editor via `:edge-types` + an `editorEdges` computed that overrides the type to `deletable` (the shared `edgesToVueFlow` stays type-neutral so the monitor keeps plain `smoothstep`). The delete button calls `useVueFlow().removeEdges([id])` -> the same `@edges-change` path. Note: `EdgeLabelRenderer` **teleports** the button out of the edge's SVG group, so a `:deep(.vue-flow__edge:hover) ...` descendant selector cannot reveal it; keep the affordance visible (or drive it from the `selected` prop), don't rely on edge-hover.
- **Fan-out is allowed.** One source handle can have many edges. `validateConnection` rejects only: self-loops, a target port other than `main`, an undeclared source port, and an *exact-duplicate* edge (same source+port+target). Never reject "this output port is already connected", and use length checks (not `?? []`) when reading a node's `outputPorts` so an empty array doesn't silently reject every connection.
- **Image-source step configs** use the shared `components/pipeline/steps/_shared/ImageSourceSelector.vue` (the source `<v-select>` plus per-source sub-config: trigger count, reCamera `CameraSelector`, time filter, pipeline path, cts_window path; step-specific extras go through its default slot). It is adopted by `image_crop`, `llm_call`, `scene_analysis`, and `person_identification`; do not re-paste the source select per config. `StepConfigDialog` fetches the CTS roster via `cts.getCameras()` and threads `ctsCameraItems` (CTS) alongside `cameraSensorItems` (reCamera) to the configs.

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
3. **Always use `useChartTheme`.** The composable at `composables/useChartTheme.js` injects the ECharts theme derived from Vuetify's current theme. Pass its `chartTheme` return value to every `v-chart` instance.

```js
// CORRECT
import { useChartTheme } from '@/composables/useChartTheme.js'
const { chartTheme } = useChartTheme()
// <v-chart :theme="chartTheme" :option="option" />

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
| `cc_theme` | `"ccDark"` or `"ccLight"` | User's preferred base theme (managed by the existing theme toggle, separate from `cc_marauders`) |

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

---

## File organization

```
frontend/
  src/
    styles/theme.css          -- global design tokens + Vuetify overrides
    services/api.js           -- all API calls
    services/contracts.js     -- response shape validation
    services/timezone.js      -- datetime formatting + constants
    composables/useNotify.js  -- snackbar notifications
    composables/useConfirm.js -- promise-based confirmation dialog
    components/common/        -- reusable shared components (LlmModelPicker, etc.)
    components/pipeline/      -- rule pipeline builder components
    components/companion/     -- senior-facing companion UI
    components/marauders/     -- Marauder's Map themed render components (isolated; see alternate themes section)
    views/admin/              -- admin dashboard views (one per resource)
  tests/                      -- mirrors src/ structure
    composables/
    views/
    components/
    router/
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

## Routine Builder

The guided-task Routine Builder in M9 is a linear step-list editor, not a Vue Flow
graph canvas. Reuse the existing SchemaForm and step-config components where they
fit, and expose per-routine policy overrides, per-step policy overrides,
completion-gate settings, and zone/camera pickers without introducing a parallel
pipeline-authoring model.

Use the guided-companion skill for the routine/session data model and domain rules:
`/home/sriram/code/nanai/cognitive-companion/.claude/skills/guided-companion/SKILL.md`.

---

## Toolchain

| Tool | Version | Notes |
| --- | --- | --- |
| Node.js | 24.16.0 LTS (Krypton) via `.nvmrc` | Use the latest active LTS patch. `frontend/package.json` engines and `frontend/Dockerfile` must match `.nvmrc`; do not run frontend checks on Node 20. |
| Vite | 8.x | Rolldown bundler default; chunk size warning threshold is 500 kB |
| Vue | 3.5.x | |
| Vue Router | 4.x (latest 4.6.x) | Router 5.x has pinia+vite peer deps and a different data-loader API; the project stays on v4 |
| Vuetify | 3.x (latest 3.12.x stable) | Vuetify 4 is a ground-up rewrite; v3 stable branch is maintained |
| ECharts | 6.x + vue-echarts 8.x | Tree-shaking API (`use()` from `echarts/core`) is the same as v5 |
| Pinia | 3.x | |

**Security**: run `npm audit --audit-level=high` before every PR. No high/critical vulnerabilities should be present. Use `npm ci` in CI (not `npm install`) to enforce the committed `package-lock.json`.

**Node enforcement**: before frontend build/test/audit work, run `nvm use $(cat frontend/.nvmrc)` from the repo root or `nvm use` inside `frontend/`. When updating Node LTS, update `.nvmrc`, `package.json` engines, `Dockerfile`, and `package-lock.json` in the same change.

---

## Verification checklist

Before marking frontend work complete:
- `cd frontend && npm run build` passes
- `npm audit --audit-level=high` reports no vulnerabilities
- No hardcoded `rgba(255,255,255,…)` or hex colors in new code
- No scoped `<style>` blocks with custom colors (utility-only scoped styles are OK)
- Data tables use server-side pagination
- Dialogs use `<v-card>` without custom classes
- Form resets in close dialogs
- `tracking-tight` on page titles
- Status chips use `statusColor()` helper
- No `v-btn-toggle` for mode/period/source pickers (use `CcSegmentedToggle`); no Vuetify material color names (`color="green|orange|purple|grey"`) -- use DS semantic colors or remove for the warm tonal default
- No undefined `--cc-*` token names (e.g. `--cc-primary`, `--cc-text-secondary`); they fall back silently
- Filter changes reset page to 1
- No `getHours()`, `getMinutes()`, `getSeconds()`, `toLocaleString()`, `toLocaleDateString()`, `toLocaleTimeString()` anywhere; use `services/timezone.js`
- Inspector drawers: `useNotify()` imported and used (zero `console.log` / `console.error` stubs)
- Inspector drawers: `useConfirm()` called before every destructive action
- Inspector drawers: `@click:row` wired on data tables (not only the Inspect button)
- Composables return `{ state, actions }` shape (never flat named refs)
- Shared composables expose one canonical key per value; mocks do not invent
  aliases absent from production
- When tests are touched: affected specs and `npm run test -- --reporter=dot` pass with no Vue, Vue Router, unresolved component, missing injection, or console warnings
- New full-app theme registered in `main.js` AND token block in a dedicated stylesheet; no body-class theming
- Mode flag owned by one composable; no direct `localStorage` reads of `cc_marauders` elsewhere
- rough.js and procedural sketches: seeded and memoized; no per-frame reseed
- Theme animations have a static reduced-motion fallback driven by `state.reducedMotion` from `useMaraudersMode()`
- Alternate theme passes WCAG AA text contrast; verify ink text on parchment background, not just visual appearance
- Toggling a theme restores the user's prior light/dark theme
