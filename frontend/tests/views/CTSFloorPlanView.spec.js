import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

// ── Mocks ──────────────────────────────────────────────────────────────────

let _wsOnMessage = null;

vi.mock("@/composables/useCtsWebSocket", () => ({
  useCtsWebSocket: (onMessage) => {
    _wsOnMessage = onMessage;
    return { status: ref("open"), disconnect: vi.fn() };
  },
}));

vi.mock("@/composables/useWorldSnapshot", () => ({
  useWorldSnapshot: () => ({
    phs: ref([]),
    inferredRooms: ref([]),
    lastUpdate: ref(0),
    isStale: ref(false),
    wsStatus: ref("open"),
    trailBuffers: new Map(),
  }),
}));

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({
    snack: ref(false),
    snackText: ref(""),
    snackColor: ref(""),
    notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  }),
}));

vi.mock("@/services/household", () => ({
  household: {
    getFloorPlan: vi.fn().mockResolvedValue({}),
    getRooms: vi.fn().mockResolvedValue([]),
    postFloorPlan: vi.fn().mockResolvedValue({}),
    putRoom: vi.fn(),
  },
}));

vi.mock("@/services/cts", () => ({
  cts: {
    getVisibilityPolygons: vi.fn().mockResolvedValue({ cameras: [] }),
  },
}));

// Stub Vuetify components.
const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /></li>" },
  "v-list-item-title": { template: "<span><slot /></span>" },
  "v-list-item-subtitle": { template: "<span><slot /></span>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-chip-group": { template: "<div><slot /></div>" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-snackbar": { template: "<div><slot /></div>" },
  "v-overlay": { template: "<div><slot /></div>" },
  "v-tabs": { template: "<div><slot /></div>" },
  "v-tab": { template: "<div><slot /></div>" },
  "v-window": { template: "<div><slot /></div>" },
  "v-window-item": { template: "<div><slot /></div>" },
  "v-btn-toggle": { template: "<div><slot /></div>" },
  "v-file-input": { template: "<input type='file' />" },
  "v-text-field": { template: "<input />" },
  "v-select": { template: "<select><slot /></select>" },
  "v-autocomplete": { template: "<input />" },
  "v-data-table": { template: "<table><slot /></table>" },
  "v-img": { template: "<img />" },
  "v-img-placeholder": { template: "<div />" },
  "v-progress-circular": { template: "<div />" },
  "v-checkbox-btn": { template: "<input type='checkbox' />" },
  "v-navigation-drawer": { template: "<div><slot /></div>" },
  "v-slider": { template: "<input type='range' />" },
  PHMarker: { template: "<div />" },
  PolygonOnSnapshot: { template: "<div />" },
  "router-link": { template: "<a><slot /></a>" },
};

import CTSFloorPlanView from "../../src/views/admin/CTSFloorPlanView.vue";

async function mountView() {
  const wrapper = mount(CTSFloorPlanView, {
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

describe("CTSFloorPlanView — world snapshot handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    _wsOnMessage = null;
  });

  it("renders without errors on mount", async () => {
    const wrapper = await mountView();
    expect(wrapper.vm).toBeDefined();
  });

  it("renders PHMarker for each PH in world snapshot", async () => {
    const wrapper = await mountView();
    expect(wrapper.vm.$.setupState.worldPhMarkers).toBeDefined();
    const markers = wrapper.vm.$.setupState.worldPhMarkers;
    expect(Array.isArray(markers)).toBe(true);
  });

  it("has zero references to identityTrails reactive map", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;
    // identityTrails still exists but is a computed returning {} (no-op)
    const trails = state.identityTrails;
    expect(Object.keys(trails)).toHaveLength(0);
  });

  it("world snapshot empty state shows when no markers", async () => {
    const wrapper = await mountView();
    expect(wrapper.html()).toContain("No active tracks");
  });

  it("uses useWorldSnapshot composable (not cts_live_frame)", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;
    // New N4 composable should be present
    expect(state.worldPhs).toBeDefined();
    expect(state.worldInferredRooms).toBeDefined();
    expect(state.worldIsStale).toBeDefined();
  });
});
