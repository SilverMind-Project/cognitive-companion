// Global test setup. Node 24 LTS ships crypto.hash natively; no shim needed.

import { createPinia, setActivePinia } from "pinia";
import { beforeEach } from "vitest";

// happy-dom (our `environment`) does not define `visualViewport` at all -- not even as
// `undefined` -- so Vuetify's VOverlay location strategy (`visualViewport?.addEventListener(...)`)
// throws ReferenceError on the bare identifier before the `?.` can short-circuit: optional
// chaining only guards a null/undefined *value*, not an unbound global. Any real component mount
// that surfaces a VOverlay (VSnackbar, VMenu, VDialog, ...) hits this. Stubbed once globally
// rather than per-spec, matching the fresh-Pinia pattern below.
if (typeof globalThis.visualViewport === "undefined") {
  globalThis.visualViewport = {
    width: 1024,
    height: 768,
    offsetLeft: 0,
    offsetTop: 0,
    scale: 1,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
}

// A fresh Pinia per test.
//
// Global rather than per-spec for two reasons: every spec that mounts a component touching a
// store would otherwise repeat the same three lines, and a *fresh* instance per test is what
// keeps store state from leaking between tests -- stores are singletons within a Pinia, so a
// shared one would reintroduce the cross-test contamination class just closed.
//
// Specs needing store behavior stubbed rather than run can still install their own
// createTestingPinia() in mount options; this only sets the fallback Pinia that useStore() resolves
// to when a component was mounted without one.
beforeEach(() => {
  setActivePinia(createPinia());
});
