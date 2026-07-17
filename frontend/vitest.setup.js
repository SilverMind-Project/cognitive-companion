// Global test setup. Node 24 LTS ships crypto.hash natively; no shim needed.

import { createPinia, setActivePinia } from "pinia";
import { beforeEach } from "vitest";

// A fresh Pinia per test (M18).
//
// Global rather than per-spec for two reasons: every spec that mounts a component touching a
// store would otherwise repeat the same three lines, and a *fresh* instance per test is what
// keeps store state from leaking between tests -- stores are singletons within a Pinia, so a
// shared one would reintroduce the cross-test contamination class M15 just closed.
//
// Specs needing store behavior stubbed rather than run can still install their own
// createTestingPinia in mount options; this only sets the fallback Pinia that useStore() resolves
// to when a component was mounted without one.
beforeEach(() => {
  setActivePinia(createPinia());
});
