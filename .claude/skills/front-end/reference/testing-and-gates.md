# Testing, gates, toolchain, and file layout

Read before writing frontend tests or declaring frontend work done. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

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
| `src/services/http.ts`, `src/services/modules/` | `tests/services/http.spec.ts`, `tests/services/modules/*.spec.ts`, `tests/services/one_request_core.spec.js`, `tests/services/api_barrel.spec.ts` |

**Never place test files inside `frontend/src/`** (e.g. `src/composables/__tests__/`). Tests are not part of the application bundle and must stay in `frontend/tests/`. `frontend/vite.config.js` pins `test.include: ["tests/**/*.{spec,test}.{js,ts}"]` so specs under `src/` never run, and `tests/architecture/test_location.spec.ts` fails CI if any spec or `__tests__/` directory appears under `src/`.

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

## File organization

```
frontend/
  src/
    styles/theme.css          -- global design tokens + Vuetify overrides
    services/http.ts          -- the one request core (typed openapi-fetch client, auth, ApiError)
    services/modules/         -- typed domain modules; all endpoint calls live here
    services/api.js           -- barrel re-exporting the modules (legacy call sites only)
    generated/api-types.d.ts  -- types generated from the backend's openapi.json
    services/timezone.js      -- datetime formatting + constants
    stores/                   -- Pinia: global/shared state (auth, appConfig, notifications, pipelineEvents, ui)
    composables/useNotify.js  -- notifications (delegates to the store; CcSnackbarHost renders)
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

## Deterministic gates

Before marking frontend work complete run:

- `npm run lint` runs ESLint (`eslint src tests --max-warnings 0`) and Stylelint (`npm run lint:style` -> `stylelint "src/**/*.vue"`):
  - **ESLint**: `no-alert`, `no-restricted-properties` (timezone discipline outside `services/timezone.js`), `vue/no-restricted-class` (`text-grey`, `text-grey-*`), `vue/no-restricted-static-attribute` (material `color` values `green|orange|purple|deep-purple|blue|red|grey|amber`), `vue/no-restricted-syntax` (`<v-snackbar>` outside `CcSnackbarHost.vue`, `<v-btn-toggle>` outside sanctioned `RegionEditor.vue`, hardcoded hex and numeric `rgb()`/`rgba()` in templates), `no-restricted-syntax` (hardcoded hex and numeric `rgb()`/`rgba()` outside `styles/**`, `src/main.js`, `useAnnotationStyle.js`, `useIdentityColor.js`, `components/marauders/**`; plus no raw `fetch()` in CTS surfaces, no `cc_api_key` `localStorage` access outside `stores/auth.ts`/`services/http.ts`, no `useNotify()` in composables, no `require('echarts')`), and `no-restricted-imports` (no full `echarts` bundle).
  - **Stylelint**: `color-no-hex`, `declaration-property-value-disallowed-list` (hardcoded numeric `rgb()`/`rgba()`, permitting Vuetify `rgb(var(--v-theme-*))` / `rgba(var(--v-theme-*), a)`), and `stylelint-config-standard-vue` CSS correctness checks.
- `npm run format:check` (Prettier), `npm run typecheck` (`vue-tsc`), `npm run build`, `npm run knip` (dead exports/files/deps -- delete findings, don't ignore them), `npm audit --audit-level=high`.
- `npx vitest run` includes architecture/guard checks:
  - `tests/architecture/test_location.spec.ts` (zero specs under `src/`, vitest `test.include` pinned)
  - `tests/architecture/lint_canary.spec.ts` (non-vacuity canary over `tests/fixtures/lint_canary/CanaryViolations.vue` for every ESLint and Stylelint rule)
  - `tests/styles/token_existence.spec.ts` (every `var(--cc-*)` and `ccToken('--cc-*')` under `src/` resolves to a defined token)
  - `tests/composables/composable_shape.spec.ts` (enforces `{ state, actions }` + read-only `ComputedRef` on server-state composables and freezes the legacy flat-return allowlist)

CI runs these gates; a rule that must be relaxed is relaxed in `eslint.config.js` or `stylelint.config.mjs` with a comment, never by sprinkling inline disables.

## Verification checklist

Judgment checks not covered by the deterministic gates above:
- No scoped `<style>` blocks overriding global surface/text colors owned by `theme.css` (utility-only scoped styles are OK)
- Data tables use server-side pagination and reset page to 1 on filter changes
- Dialogs use `AppDialog` (or plain persistent `<v-dialog>` + `<v-card>` only for `useConfirm()`) and reset forms on close
- `tracking-tight` on page titles
- Status chips use `statusColor()` helper
- A server-paged list uses `v-data-table-server`, never `v-data-table` with `:items-length`
- Inspector drawers: `useNotify()` imported and used (zero `console.log` / `console.error` stubs), `useConfirm()` called before every destructive action, and `@click:row` wired on data tables (not only the Inspect button)
- No module-level `ref`/`reactive` shared across components (that belongs in a Pinia store)
- Shared composables expose one canonical key per value; test mocks do not invent aliases absent from production
- When tests are touched: affected specs and `npm run test -- --reporter=dot` pass with no Vue, Vue Router, unresolved component, missing injection, or console warnings
- New full-app theme registered in `main.js` AND token block in a dedicated stylesheet; no body-class theming
- Mode flag owned by one composable; no direct `localStorage` reads of `cc_marauders` elsewhere
- rough.js and procedural sketches: seeded and memoized; no per-frame reseed
- Theme animations have a static reduced-motion fallback driven by `state.reducedMotion` from `useMaraudersMode()`
- Alternate theme passes WCAG AA text contrast; verify ink text on parchment background, not just visual appearance
- Toggling a theme restores the user's prior theme
