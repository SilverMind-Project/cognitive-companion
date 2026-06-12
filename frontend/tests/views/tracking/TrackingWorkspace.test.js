/**
 * U4-T1: TrackingWorkspace
 *
 * Verifies:
 * - Renders the panel tab set
 * - The `panel` query param selects the active panel
 * - An unknown panel falls back to the role default
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";

// ── Mutable route stub (top-level, mutated per test) ────────────────────────
const mockQuery = { panel: "" };
const mockReplace = vi.fn();

vi.mock("vue-router", () => ({
  useRoute:  () => ({ query: mockQuery }),
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/composables/usePersonPresence.js", () => ({
  usePersonPresence: () => ({
    locations: ref([]),
    loading: ref(false),
    error: ref(null),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/views/tracking/panels/OverviewPanel.vue",          () => ({ default: { template: '<div data-testid="panel-overview" />' } }));
vi.mock("@/views/tracking/panels/LiveFloorPanel.vue",         () => ({ default: { template: '<div data-testid="panel-live-floor" />' } }));
vi.mock("@/views/tracking/panels/MobilityPanel.vue",          () => ({ default: { template: '<div data-testid="panel-mobility" />' } }));
vi.mock("@/views/tracking/panels/PeoplePanel.vue",            () => ({ default: { template: '<div data-testid="panel-people" />' } }));
vi.mock("@/views/tracking/panels/PresenceTimelinePanel.vue",  () => ({ default: { template: '<div data-testid="panel-presence-timeline" />' } }));
vi.mock("@/views/tracking/panels/SignalsPanel.vue",           () => ({ default: { template: '<div data-testid="panel-signals" />' } }));
vi.mock("@/views/tracking/panels/ReportsPanel.vue",           () => ({ default: { template: '<div data-testid="panel-reports" />' } }));

import TrackingWorkspace from "../../../src/views/tracking/TrackingWorkspace.vue";

const stubs = {
  "v-tabs":        { template: '<div><slot /></div>' },
  "v-tab":         { template: '<button :value="$attrs.value"><slot /></button>', props: ["value"] },
  "v-window":      { template: '<div><slot /></div>' },
  "v-window-item": { template: '<div><slot /></div>', props: ["value"] },
};

function mountWorkspace(queryPanel = "", props = {}) {
  mockQuery.panel = queryPanel;
  return mount(TrackingWorkspace, { props, global: { stubs } });
}

beforeEach(() => {
  mockReplace.mockClear();
  mockQuery.panel = "";
});

describe("TrackingWorkspace", () => {
  it("renders one page-level heading and a labelled section navigation", () => {
    const w = mountWorkspace();

    expect(w.get("h1").text()).toBe("Tracking");
    expect(w.get("nav").attributes("aria-label")).toBe("Tracking workspace sections");
  });

  it("renders all 6 panel tabs for admin role", () => {
    const w = mountWorkspace();
    const ids = w.vm.visibleTabs.map((t) => t.id);
    expect(ids).toContain("overview");
    expect(ids).toContain("live-floor");
    expect(ids).toContain("people");
    expect(ids).toContain("presence-timeline");
    expect(ids).toContain("signals");
    expect(ids).toContain("reports");
  });

  it("defaults to overview panel for admin role with no panel query", () => {
    const w = mountWorkspace("");
    expect(w.vm.activePanel).toBe("overview");
  });

  it("selects the signals panel when panel=signals is in query", () => {
    const w = mountWorkspace("signals");
    expect(w.vm.activePanel).toBe("signals");
  });

  it("selects presence-timeline for panel=presence-timeline", () => {
    const w = mountWorkspace("presence-timeline");
    expect(w.vm.activePanel).toBe("presence-timeline");
  });

  it("unknown panel falls back to role default (admin → overview)", () => {
    const w = mountWorkspace("nonexistent-panel");
    expect(w.vm.activePanel).toBe("overview");
  });

  it("caregiver role: visibleTabs does not include overview or signals", () => {
    const w = mountWorkspace("", { role: "caregiver" });
    const ids = w.vm.visibleTabs.map((t) => t.id);
    expect(ids).not.toContain("overview");
    expect(ids).not.toContain("signals");
    expect(ids).toContain("presence-timeline");
  });

  it("caregiver role: default panel is presence-timeline", () => {
    const w = mountWorkspace("", { role: "caregiver" });
    expect(w.vm.activePanel).toBe("presence-timeline");
  });

  it("medical role: default panel is signals", () => {
    const w = mountWorkspace("", { role: "medical" });
    expect(w.vm.activePanel).toBe("signals");
  });
});
