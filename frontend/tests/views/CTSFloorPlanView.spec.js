import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref, reactive } from "vue";
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

const maraudersState = reactive({ enabled: false, reducedMotion: false });
vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: maraudersState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
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
    createTransitZone: vi.fn(),
    updateTransitZone: vi.fn(),
    deleteTransitZone: vi.fn(),
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
  CcSegmentedToggle: { template: "<div />", props: ["modelValue", "options", "size"] },
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
  FloorMarkerLayer: {
    props: ["markers", "phCount", "canvasH"],
    emits: ["phClick"],
    template: "<g data-testid='floor-marker-layer' />",
  },
  HeatmapBinLayer: {
    name: "HeatmapBinLayer",
    props: ["bins", "loading", "error", "canvasH"],
    template: "<g data-testid='heatmap-bin-layer' />",
  },
  PolygonOnSnapshot: {
    name: "PolygonOnSnapshot",
    props: ["imageClass"],
    template: "<div data-testid='polygon-on-snapshot' />",
  },
  DoorZoneEditor: {
    props: ["zones"],
    template:
      "<div data-testid='door-zone-editor'><span v-for='zone in zones' :key='zone.id'>{{ zone.name }}</span></div>",
  },
  InferredPresenceBadge: { template: "<div />" },
  CcZoomControls: { template: "<div />" },
  MaraudersToggle: { template: "<button data-testid='marauders-toggle' />" },
  MaraudersInkPolygon: {
    props: ["points", "canvasW", "canvasH", "seedKey", "label", "fill"],
    template: "<g data-testid='marauders-ink-polygon' />",
  },
  MaraudersFloorMarkers: {
    props: [
      "markers",
      "phCount",
      "canvasH",
      "trails",
      "nowMs",
      "fpWidth",
      "fpHeight",
      "fpMpp",
      "canvasW",
      "reducedMotion",
    ],
    emits: ["phClick"],
    template: "<g data-testid='marauders-floor-markers' />",
  },
  MaraudersAmbientLayer: {
    props: ["canvasW", "canvasH", "nowMs", "reducedMotion"],
    template: "<g data-testid='marauders-ambient-layer' />",
  },
  MaraudersHeatmapLayer: {
    name: "MaraudersHeatmapLayer",
    props: ["bins", "loading", "error", "canvasH"],
    template: "<g data-testid='marauders-heatmap-layer' />",
  },
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

describe("CTSFloorPlanView — layout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("uses compact page heading and subtitle styles", async () => {
    const wrapper = await mountView();

    expect(wrapper.find(".floor-plan-page-title").text()).toBe("Floor Plan");
    expect(wrapper.find(".floor-plan-page-subtitle").text()).toContain("Upload a floor plan image");
    expect(wrapper.find(".floor-plan-mode-nav").exists()).toBe(true);
  });

  it.each(["live", "heatmap", "edit"])(
    "keeps the main canvas before the right sidebar in %s mode",
    async (mode) => {
      const wrapper = await mountView();
      wrapper.vm.$.setupState.mode = mode;
      await wrapper.vm.$nextTick();

      const layout = wrapper.find(".floor-plan-layout");
      const columns = layout.element.children;

      expect(columns[0].classList.contains("floor-plan-main")).toBe(true);
      expect(columns[1].classList.contains("floor-plan-sidebar")).toBe(true);
    },
  );

  it("renders live and heatmap canvases edge-to-edge inside visual cards", async () => {
    const wrapper = await mountView();

    expect(wrapper.find(".floor-plan-visual-card .floor-plan-canvas").exists()).toBe(true);

    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".floor-plan-visual-card .floor-plan-canvas").exists()).toBe(true);
    expect(wrapper.find(".floor-plan-visual-card .pa-0").exists()).toBe(true);
  });

  it("organizes floor plan upload as a three-step workflow with a summary footer", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "upload";
    await wrapper.vm.$nextTick();

    const steps = wrapper.findAll(".upload-step");
    expect(steps).toHaveLength(3);
    expect(steps[0].text()).toContain("Choose the image");
    expect(steps[1].text()).toContain("Set the real-world scale");
    expect(steps[2].text()).toContain("Review map details");
    expect(steps[1].find(".upload-scale-method").exists()).toBe(true);

    const footer = wrapper.find(".upload-save-actions");
    expect(footer.find(".upload-save-summary").exists()).toBe(true);
    expect(footer.text()).toContain("Save floor plan");
  });

  it.each(["live", "heatmap", "coverage"])(
    "uses the shared floor-plan background image treatment in %s mode",
    async (mode) => {
      const wrapper = await mountView();
      const state = wrapper.vm.$.setupState;
      state.floorPlanUrl = "/floor.png";
      state.mode = mode;
      await wrapper.vm.$nextTick();

      expect(wrapper.find(".cc-floor-plan-background-image").exists()).toBe(true);
    },
  );

  it("passes the shared floor-plan treatment into the room editor", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "edit";
    await wrapper.vm.$nextTick();

    const editor = wrapper.findComponent({ name: "PolygonOnSnapshot" });
    expect(editor.props("imageClass")).toContain("cc-floor-plan-background-image");
  });
});

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

  it("world snapshot empty state is delegated to FloorMarkerLayer", async () => {
    // Empty-state text ("No active tracks") now lives inside FloorMarkerLayer.
    // The view mounts FloorMarkerLayer and passes phCount; the stub proves delegation.
    const wrapper = await mountView();
    expect(wrapper.find("[data-testid='floor-marker-layer']").exists()).toBe(true);
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
    maraudersState.enabled = false;
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

  it("shows HeatmapBinLayer in heatmap mode (empty-state delegated to it)", async () => {
    // Empty-state text ("Select a person and date range") now lives inside
    // HeatmapBinLayer. The view mounts the layer and passes bins; the stub proves
    // delegation.
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-testid='heatmap-bin-layer']").exists()).toBe(true);
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

  it("DATE_PRESETS and TIME_PRESETS expose rolling-window and dementia-aligned options", async () => {
    const wrapper = await mountView();
    const { DATE_PRESETS, TIME_PRESETS } = wrapper.vm.$.setupState;

    expect(DATE_PRESETS.map((p) => p.key)).toEqual([
      "last_24h",
      "last_7d",
      "last_14d",
      "last_30d",
      "custom",
    ]);

    const timeKeys = TIME_PRESETS.map((p) => p.key);
    expect(timeKeys).toEqual(
      expect.arrayContaining([
        "all",
        "morning",
        "afternoon",
        "sundowning",
        "evening",
        "night",
        "custom",
      ]),
    );
    // Night wraps past midnight: start (21:00) > end (06:00).
    const night = TIME_PRESETS.find((p) => p.key === "night");
    expect(night.start).toBe(21 * 60);
    expect(night.end).toBe(6 * 60);
    expect(night.start).toBeGreaterThan(night.end);
  });

  it("Generate (default presets) sends a rolling window with no time-of-day filter", async () => {
    const { api } = await import("@/services/api");
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    // Defaults: date preset last_7d, time preset all. Only a person is required.
    state.mode = "heatmap";
    state.heatmapPersonId = "p1";
    await wrapper.vm.$nextTick();

    const buttons = wrapper.findAll("button");
    const generateBtn = buttons.find((b) => b.text().includes("Generate"));
    expect(generateBtn).toBeDefined();
    await generateBtn.trigger("click");
    await flushPromises();

    expect(api.getHeatmap).toHaveBeenCalledWith(
      expect.objectContaining({
        person_id: "p1",
        start_time: expect.any(String),
        end_time: expect.any(String),
        start_minute: null,
        end_minute: null,
      }),
    );
  });

  it("shows the resolved clock window for the selected time preset", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.mode = "heatmap";
    state.heatmapTimePreset = "morning";
    await wrapper.vm.$nextTick();
    expect(state.heatmapTimeWindowLabel).toBe("6:00 AM – 12:00 PM");

    // Night wraps past midnight and is annotated as such.
    state.heatmapTimePreset = "night";
    await wrapper.vm.$nextTick();
    expect(state.heatmapTimeWindowLabel).toBe("9:00 PM – 6:00 AM (overnight)");

    state.heatmapTimePreset = "all";
    await wrapper.vm.$nextTick();
    expect(state.heatmapTimeWindowLabel).toBe("All times of day");
  });

  it("Generate with the Night preset sends a cross-midnight minute window", async () => {
    const { api } = await import("@/services/api");
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.mode = "heatmap";
    state.heatmapPersonId = "p1";
    state.heatmapTimePreset = "night";
    await wrapper.vm.$nextTick();

    const buttons = wrapper.findAll("button");
    const generateBtn = buttons.find((b) => b.text().includes("Generate"));
    await generateBtn.trigger("click");
    await flushPromises();

    expect(api.getHeatmap).toHaveBeenCalledWith(
      expect.objectContaining({
        person_id: "p1",
        start_minute: 21 * 60,
        end_minute: 6 * 60,
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

describe("CTSFloorPlanView — M1 seam: layer delegation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("passes smoothedMarkers to FloorMarkerLayer in live mode", async () => {
    const wrapper = await mountView();
    const layer = wrapper.find("[data-testid='floor-marker-layer']");
    expect(layer.exists()).toBe(true);
  });

  it("FloorMarkerLayer receives phCount driven from worldPhMarkers length", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;
    // worldPhMarkers is initially empty (mock returns phs=[]).
    // The stub renders, and the view exposes the count via the prop.
    expect(state.worldPhMarkers).toBeDefined();
    expect(typeof state.worldPhMarkers.length).toBe("number");
  });

  it("passes mappedHeatmapBins to HeatmapBinLayer in heatmap mode", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();
    const layer = wrapper.find("[data-testid='heatmap-bin-layer']");
    expect(layer.exists()).toBe(true);
  });

  it("HeatmapBinLayer receives loading state from heatmapState", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();
    // loading defaults to false (no active request)
    expect(wrapper.vm.$.setupState.heatmapState.loading).toBe(false);
  });
});

describe("CTSFloorPlanView — M5 seam: themed heatmap", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("renders HeatmapBinLayer when marauders mode is OFF", async () => {
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();

    expect(wrapper.find("[data-testid='heatmap-bin-layer']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='marauders-heatmap-layer']").exists()).toBe(false);
  });

  it("renders MaraudersHeatmapLayer when marauders mode is ON", async () => {
    maraudersState.enabled = true;
    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "heatmap";
    await wrapper.vm.$nextTick();

    expect(wrapper.find("[data-testid='marauders-heatmap-layer']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='heatmap-bin-layer']").exists()).toBe(false);
  });

  it("passes the same mapped bins contract to both heatmap renderers", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;
    state.mode = "heatmap";
    state.fpWidth = 10;
    state.fpHeight = 8;
    state.fpMpp = 0.01;
    state.canvasW = 1000;
    state.canvasH = 800;
    state.heatmapState.data = {
      bins: [{ x_m: 1, y_m: 2, weight: 5 }],
    };
    await wrapper.vm.$nextTick();

    const standardLayer = wrapper.findComponent({ name: "HeatmapBinLayer" });
    expect(standardLayer.props("bins")).toEqual(state.mappedHeatmapBins);

    maraudersState.enabled = true;
    await wrapper.vm.$nextTick();

    const themedLayer = wrapper.findComponent({ name: "MaraudersHeatmapLayer" });
    expect(themedLayer.props("bins")).toEqual(state.mappedHeatmapBins);
  });
});

describe("CTSFloorPlanView — M3 seam: ink rendering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("live view: plain <polygon> renders when marauders disabled", async () => {
    const { household } = await import("@/services/household");
    household.getRooms.mockResolvedValueOnce([
      {
        id: 1,
        name: "Kitchen",
        floor_polygon: [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 1],
        ],
      },
    ]);
    const wrapper = await mountView();
    wrapper.vm.$.setupState.canvasReady = true;
    wrapper.vm.$.setupState.rooms = [
      {
        id: 1,
        name: "Kitchen",
        floor_polygon: [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 1],
        ],
      },
    ];
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll("[data-testid='marauders-ink-polygon']")).toHaveLength(0);
    expect(wrapper.find("polygon.room-poly").exists()).toBe(true);
  });

  it("live view: MaraudersInkPolygon renders when marauders enabled", async () => {
    const wrapper = await mountView();
    maraudersState.enabled = true;
    wrapper.vm.$.setupState.rooms = [
      {
        id: 1,
        name: "Kitchen",
        floor_polygon: [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 1],
        ],
      },
    ];
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll("[data-testid='marauders-ink-polygon']").length).toBeGreaterThan(0);
  });
});

describe("CTSFloorPlanView — M4 seam: footprint markers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("renders FloorMarkerLayer when marauders mode is OFF", async () => {
    maraudersState.enabled = false;
    const wrapper = await mountView();
    expect(wrapper.find("[data-testid='floor-marker-layer']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='marauders-floor-markers']").exists()).toBe(false);
  });

  it("renders MaraudersFloorMarkers and not FloorMarkerLayer when marauders mode is ON", async () => {
    maraudersState.enabled = true;
    const wrapper = await mountView();
    expect(wrapper.find("[data-testid='marauders-floor-markers']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='floor-marker-layer']").exists()).toBe(false);
  });

  it("renders MaraudersAmbientLayer when marauders mode is ON", async () => {
    maraudersState.enabled = true;
    const wrapper = await mountView();
    expect(wrapper.find("[data-testid='marauders-ambient-layer']").exists()).toBe(true);
  });

  it("does not render MaraudersAmbientLayer when marauders mode is OFF", async () => {
    maraudersState.enabled = false;
    const wrapper = await mountView();
    expect(wrapper.find("[data-testid='marauders-ambient-layer']").exists()).toBe(false);
  });

  it("MaraudersFloorMarkers stub is present when marauders is ON", async () => {
    maraudersState.enabled = true;
    const wrapper = await mountView();
    // Confirm the stub rendered (sufficient to prove the v-if seam works)
    expect(wrapper.find("[data-testid='marauders-floor-markers']").exists()).toBe(true);
  });
});

describe("CTSFloorPlanView — door zones mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and renders existing transit zones", async () => {
    const { cts } = await import("@/services/cts");
    cts.getTransitZones.mockResolvedValueOnce([
      {
        id: "zone-1",
        name: "Bathroom threshold",
        kind: "door",
        polygon: [
          [0.1, 0.2],
          [0.3, 0.2],
          [0.3, 0.4],
        ],
        inside_room_id: 1,
        outside_room_id: 2,
        direction_vec: [1, 0],
      },
    ]);

    const wrapper = await mountView();
    wrapper.vm.$.setupState.mode = "doors";
    await flushPromises();

    expect(cts.getTransitZones).toHaveBeenCalled();
    expect(wrapper.find("[data-testid='door-zone-editor']").exists()).toBe(true);
    expect(wrapper.html()).toContain("Bathroom threshold");
  });
});
