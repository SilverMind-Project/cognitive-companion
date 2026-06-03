import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

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
    getTransitZones: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("@/services/api", () => ({
  api: {
    getPersons: vi.fn().mockResolvedValue([
      { id: "p1", name: "Grandma" },
      { id: "p2", name: "Bob" },
    ]),
    getHeatmap: vi.fn().mockResolvedValue({
      person_id: "p1",
      bins: [
        { x_m: 1.0, y_m: 2.0, weight: 5 },
        { x_m: 3.5, y_m: 0.5, weight: 2 },
      ],
    }),
  },
}));


// Stub Vuetify components.
const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-item": { template: "<div><slot /></div>" },
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
  InferredPresenceBadge: { template: "<div />" },
  CcZoomControls: { template: "<div />" },
  "router-link": { template: "<a><slot /></a>" },
};

import CTSFloorPlanView from "../../src/views/admin/CTSFloorPlanView.vue";

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
  await router.push("/");
  await router.isReady();

  const wrapper = mount(CTSFloorPlanView, {
    global: { plugins: [router], stubs: stubComponents },
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

  it("does not expose an identityTrails reactive map (removed in N4 refactor)", async () => {
    const wrapper = await mountView();
    // identityTrails was removed when the world-snapshot composable took over
    // trail management. The property no longer exists on the setup state.
    expect(wrapper.vm.$.setupState.identityTrails).toBeUndefined();
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

describe("CTSFloorPlanView — heatmap mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Heatmap mode button", async () => {
    const wrapper = await mountView();
    expect(wrapper.html()).toContain("Heatmap");
  });

  it("shows heatmap controls panel when mode is heatmap", async () => {
    const wrapper = await mountView();
    // Use the proxy setter so the ref is correctly updated
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();
    expect(wrapper.html()).toContain("Filters");
    expect(wrapper.html()).toContain("Generate");
  });

  it("shows empty-state prompt in heatmap mode", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();
    expect(wrapper.html()).toContain("Select a person and date range");
  });

  it("mappedHeatmapBins is empty when no floor plan config", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;
    expect(state.mappedHeatmapBins).toBeDefined();
    // fpWidth/fpHeight/fpMpp are null by default
    expect(state.mappedHeatmapBins.length).toBe(0);
  });

  it("mappedHeatmapBins maps bins when floor plan and data are set", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    // Provide floor plan config via proxy setter (unwraps refs automatically)
    state.fpWidth = 10;
    state.fpHeight = 8;
    state.fpMpp = 0.01;
    state.canvasW = 1000;
    state.canvasH = 800;

    // Inject heatmap data directly into the reactive state object
    state.heatmapState.data = {
      person_id: "p1",
      bins: [
        { x_m: 1.0, y_m: 2.0, weight: 10 },
        { x_m: 3.5, y_m: 0.5, weight: 5 },
      ],
    };
    await wrapper.vm.$nextTick();

    expect(state.mappedHeatmapBins.length).toBe(2);
    // Highest-weight bin gets opacity 1.0 (0.2 + 0.8 * 10/10)
    expect(state.mappedHeatmapBins[0].opacity).toBeCloseTo(1.0, 3);
    // Second bin gets half-weight opacity
    expect(state.mappedHeatmapBins[1].opacity).toBeCloseTo(0.6, 3);
  });

  it("HOUR_PRESETS covers all day, morning, afternoon, evening, night", async () => {
    const wrapper = await mountView();
    const presets = wrapper.vm.$.setupState.HOUR_PRESETS;
    expect(presets.length).toBe(5);
    expect(presets[0].startHour).toBeNull();
    expect(presets[1].label).toContain("Morning");
    expect(presets[4].label).toContain("Night");
  });

  it("Generate button triggers api.getHeatmap with correct params", async () => {
    const { api } = await import("@/services/api");
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    // Switch to heatmap mode and populate required fields
    state.mode = "heatmap";
    state.heatmapPersonId = "p1";
    state.heatmapStartDate = "2026-05-01";
    state.heatmapEndDate = "2026-05-07";
    await wrapper.vm.$nextTick();

    // Click the Generate button (last button rendered in heatmap mode)
    const buttons = wrapper.findAll("button");
    const generateBtn = buttons.find((b) => b.text().includes("Generate"));
    expect(generateBtn).toBeDefined();
    await generateBtn.trigger("click");
    await flushPromises();

    expect(api.getHeatmap).toHaveBeenCalledWith(
      expect.objectContaining({
        person_id: "p1",
        start_time: "2026-05-01T00:00:00Z",
        end_time: "2026-05-07T23:59:59Z",
      }),
    );
  });

  it("changing to heatmap mode loads persons via api.getPersons", async () => {
    const { api } = await import("@/services/api");
    const wrapper = await mountView();

    wrapper.vm.$.setupState.mode = "heatmap";
    await flushPromises();

    expect(api.getPersons).toHaveBeenCalled();
  });
});
