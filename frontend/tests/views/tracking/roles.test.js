/**
 * U4-T6: Role-aware workspace (D4)
 *
 * Verifies:
 * - Admin default panel: overview; all 6 panels visible
 * - Caregiver default panel: presence-timeline; overview/signals not visible
 * - Medical default panel: signals; overview not visible
 * - Non-permitted panels absent from visibleTabs
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";

vi.mock("@/composables/usePersonPresence.js", () => ({
  usePersonPresence: () => ({ locations: ref([]), loading: ref(false), error: ref(null), refresh: vi.fn() }),
}));

vi.mock("vue-router", () => ({
  useRoute:  () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@/views/tracking/panels/OverviewPanel.vue",          () => ({ default: { template: '<div />' } }));
vi.mock("@/views/tracking/panels/LiveFloorPanel.vue",         () => ({ default: { template: '<div />' } }));
vi.mock("@/views/tracking/panels/PeoplePanel.vue",            () => ({ default: { template: '<div />' } }));
vi.mock("@/views/tracking/panels/PresenceTimelinePanel.vue",  () => ({ default: { template: '<div />' } }));
vi.mock("@/views/tracking/panels/SignalsPanel.vue",           () => ({ default: { template: '<div />' } }));
vi.mock("@/views/tracking/panels/ReportsPanel.vue",           () => ({ default: { template: '<div />' } }));

import TrackingWorkspace from "../../../src/views/tracking/TrackingWorkspace.vue";

const stubs = {
  "v-tabs":        { template: '<div><slot /></div>' },
  "v-tab":         { template: '<button><slot /></button>', props: ["value"] },
  "v-window":      { template: '<div><slot /></div>' },
  "v-window-item": { template: '<div><slot /></div>', props: ["value"] },
};

function mountRole(role) {
  return mount(TrackingWorkspace, { props: { role }, global: { stubs } });
}

describe("TrackingWorkspace role-aware (D4)", () => {
  describe("admin", () => {
    it("default panel is overview", () => {
      expect(mountRole("admin").vm.activePanel).toBe("overview");
    });
    it("all 6 panels are visible", () => {
      expect(mountRole("admin").vm.visibleTabs).toHaveLength(6);
    });
  });

  describe("caregiver", () => {
    it("default panel is presence-timeline", () => {
      expect(mountRole("caregiver").vm.activePanel).toBe("presence-timeline");
    });
    it("overview is NOT in visibleTabs", () => {
      expect(mountRole("caregiver").vm.visibleTabs.map((t) => t.id)).not.toContain("overview");
    });
    it("signals is NOT in visibleTabs", () => {
      expect(mountRole("caregiver").vm.visibleTabs.map((t) => t.id)).not.toContain("signals");
    });
    it("people IS in visibleTabs", () => {
      expect(mountRole("caregiver").vm.visibleTabs.map((t) => t.id)).toContain("people");
    });
  });

  describe("medical", () => {
    it("default panel is signals", () => {
      expect(mountRole("medical").vm.activePanel).toBe("signals");
    });
    it("overview is NOT in visibleTabs", () => {
      expect(mountRole("medical").vm.visibleTabs.map((t) => t.id)).not.toContain("overview");
    });
    it("signals IS in visibleTabs", () => {
      expect(mountRole("medical").vm.visibleTabs.map((t) => t.id)).toContain("signals");
    });
    it("reports IS in visibleTabs", () => {
      expect(mountRole("medical").vm.visibleTabs.map((t) => t.id)).toContain("reports");
    });
  });

  it("unknown role falls back to admin config (shows all 6 panels)", () => {
    expect(mountRole("unknown_role").vm.visibleTabs).toHaveLength(6);
    expect(mountRole("unknown_role").vm.activePanel).toBe("overview");
  });
});
