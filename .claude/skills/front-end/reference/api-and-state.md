# API calls, state, and composables

Read before adding an endpoint call, a store, or a composable. Part of the `front-end` skill; the rules summary is in `../SKILL.md`.

## Composables: the `{ state, actions }` shape

Extract duplicated view logic into composables under `frontend/src/composables/`. Existing shared composables include:

| Composable | Replaces |
| --- | --- |
| `useCtsSeverity.js` | `severityColor()` / `severityIcon()` duplicated across 3 views |
| `useFormatRelative.js` | `formatRelative()` duplicated across 2 views |
| `useCtsWebSocket.js` | Ad-hoc WebSocket lifecycle with no reconnection; adds 3-second exponential backoff |
| `usePHList.js` | PH list fetch, pagination, WS update handling |
| `usePHDetail.js` | PH detail fetch (observations, trail, co-present) with `Promise.allSettled` |
| `useIdentityCorrection.js` | Identity correction targets, segment proposal, apply, compensation, and job polling for the Keyframes surface and the PH inspector |
| `usePresenceTimeline.js` | Presence timeline fetch, dwell totals, WS live update, active segment timer |
| `useWorldSnapshot.js` | World snapshot WS subscription, PH marker map, 30s trail buffer, inferred rooms |

### Required composable shape: `{ state, actions }`

**All composables that manage server state must return a `{ state, actions }` object.** This is the project standard, modelled on `useCtsWebSocket.js`.

```js
export function useMyResource() {
  const state = reactive({
    items: [],
    total: 0,
    loading: false,
    error: null,
    page: 1,
    itemsPerPage: 20,
  })

  async function fetchItems() { ... }
  function onPageOptions({ page, itemsPerPage }) { ... }

  return {
    state,
    actions: { fetchItems, onPageOptions },
  }
}
```

**Return `state` and `actions`; read-only `computed` values may also be returned at the top level. Never return a raw `ref`, or a function outside `actions`** (`return { items, total, loading, fetchItems }` is wrong). The `{ state, actions }` shape:
- Makes destructuring explicit: `const { state, actions } = useMyResource()`
- Groups reactive data vs. functions clearly
- Prevents naming collisions when multiple composables are used in the same view
- Makes it obvious in the template what is state (`state.items`) vs. an action (`actions.fetchItems()`)

**Rules:**
- All reactive data (refs, reactive objects) lives under `state`
- All functions (fetch, setFilter, onPageOptions, handlers) live under `actions`
- Each returned value has one canonical key. Do not return the same ref,
  computed, object, or function under multiple names.
- WS subscriptions are wired inside the composable body (not in the view)
- Cleanup (timers, WS unsubscribe) uses `onUnmounted()` inside the composable
- Composables never call `useNotify()` internally; they accept a `notify` callback if feedback is needed, or they export an `error` state field and let the view decide how to show it.

Use design tokens (`var(--cc-*)`) or Vuetify theme colors for all CSS color values. Never hardcode hex values like `'#4CAF50'` or `'#fff'` in templates.

## API and contracts

### Adding new API methods

All HTTP goes through `src/services/http.ts`, the typed `openapi-fetch` client. Domain modules
under `src/services/modules/` own endpoint calls; components never call `fetch`.

```ts
// src/services/modules/my_resource.ts
import { client, unwrap } from "@/services/http";

export const getMyResource = (id: string) =>
  unwrap(client.GET("/api/v1/my-resource/{resource_id}", { params: { path: { resource_id: id } } }));
```

- New code is TypeScript (`.ts`, or `<script setup lang="ts">`), and is fully strict.
- Types come from `src/generated/api-types.d.ts`. Regenerate with `npm run generate:api` after
  any backend contract change; CI diff-gates both `openapi.json` and the generated types.
- **Never hand-write a response interface for a backend endpoint.** If the type is missing or
  comes out `unknown`, the backend route is missing `response_model` -- fix it there, not here.
- Errors are `ApiError` (`status` + `detail`); `error.message` keeps its historical shape.
- Never interpolate a value into a path or query string. Pass `params`; the client encodes.
- `npm run typecheck` (`vue-tsc`) is part of `make check-all`.

### There are no hand-written response contracts

`contracts.js` -- a dev-only, console-warning shape checker whose validator silently accepted
any array-of-shape spec, so several of its contracts never validated anything -- was deleted.
Do not reintroduce it or anything like it. The backend's `response_model` is the contract,
`openapi.json` is its serialization, and the generated types are how the browser sees it.

`api.js` is now a barrel: it only re-exports the domain modules so existing `api.x(...)` call
sites keep working. Do not add methods to it.

`tests/services/one_request_core.spec.js` enforces the above (no `fetch` outside `http.ts`, no
module reading the API key itself, no `contracts.js`); `eslint.config.js` enforces the component
side (no raw `fetch` in the CTS surface, no direct API-key storage access), replacing the deleted
`r4_bypass_guard.spec.js`.

### One endpoint owns each fact; no cross-contract fallbacks

Do not wrap a fetch in a `try/catch` whose fallback recovers the **same** fact from a **different** endpoint's envelope -- e.g. "if `getSampleImage()` fails, dig the URL out of `getMediaBuffer().items[0].images[0].url`". This couples the component to a contract shape it does not own. When the `media.buffer` envelope migrated from a raw array to `{items, total}`, this fallback in `ImageCropConfig` had to be hand-patched even though nothing about crop sampling changed -- a component dragged into every unrelated contract migration. The fallback's `catch {}` also swallows the real error. This is the consumer-side twin of the data-ownership rule below (single fetch owner): one source of truth per fact, on the producer side *and* the consumer side.

Fix order when you reach for such a fallback:
1. A dedicated endpoint usually already covers the case (here `/pipeline/image-sources/sample` already resolved both reCamera and CTS). Call it alone, `notify.error(...)` on failure, and delete the fallback.
2. Only if no endpoint covers the case, add coverage server-side. Never client-composite one fact out of an envelope that exists to serve a different fact.

Legitimate composition -- a view fetching two *distinct* facts from two endpoints -- is unaffected. The rule targets re-deriving one fact from a contract you do not own.

## State management

Global and shared state lives in Pinia stores under `src/stores/`. Stores are written in
TypeScript against the generated API types.

| Store | Owns |
|---|---|
| `auth.ts` | The API key. The only file allowed to touch the `cc_api_key` storage key; `http.ts` reads it through `setApiKeyProvider`, wired in `main.js`. |
| `appConfig.ts` | App-info lifecycle (timezone, name, version). Fetch only: `services/timezone.js` stays the formatting engine, and its localStorage-per-call design is a deliberate HMR fix. Do not route formatters through the store. |
| `notifications.ts` | The notification queue. |
| `pipelineEvents.ts` | The one `/ws/pipeline` socket, reference-counted across consumers. |
| `ui.ts` | Marauders mode, reduced-motion, blur mode. |

The boundary: a composable is the right home for view-local or per-instance state. A `reactive`
or `ref` declared at module top level and shared across components is a store wearing a
composable's clothes, and must be migrated when touched. Per-instance state built from injected
dependencies stays a composable (see `useKioskMode`, which documents why).

A composable may remain the public API over a store when it must run in a setup context:
`useMaraudersMode` acquires the Vuetify theme via `useTheme()` and hands it to `ui.init(theme)`.

**Notifications**: call `useNotify()` (or `useNotificationsStore()` directly). Never render a
local `<v-snackbar>` for app feedback -- `CcSnackbarHost` in `App.vue` is the single renderer,
and a per-view snackbar only ever shows messages raised by that view, which is the bug this
replaced.

**Testing**: `vitest.setup.js` installs a fresh Pinia before every test, so specs mounting
store-backed components need no boilerplate. Install `createTestingPinia` in mount options only
when a spec needs store actions stubbed rather than executed.

## Composables

### `useNotify()`
```js
const { notify } = useNotify();
notify.success("Created.");
notify.error("Failed: " + err.message);
notify.warning("Validation message");
```
No template wiring: `CcSnackbarHost` renders it. Do not add a `<v-snackbar>` to the view.

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

## Signal kind presentation

Signal kinds reach the frontend only via the generated vocabulary (`make contracts` +
`npm run generate:api`, landing in `frontend/src/generated/vocabularies.json`); presentational
extras (icon, blurb) live solely in `frontend/src/constants/signalKinds.js`
(`getKindPresentation(kind)`) with a mandatory generic fallback for unknown kinds. Never
hand-type a kind list in a component, and never build a second per-kind icon/label map --
`SignalsPanel.vue` is the reference consumer. A kind this registry has never heard of must
still render (humanized label, default icon), not throw or show `undefined`; this is the
platform forward-compatibility rule (`cts_contracts/signals.py`) and is pinned by a dedicated
unknown-kind-fallback spec that must exist before a new milestone extends the map.
