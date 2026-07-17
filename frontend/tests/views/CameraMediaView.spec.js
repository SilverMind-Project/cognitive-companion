import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import { mount } from "@vue/test-utils";

const camera = {
  camera_id: "camera-1",
  origin: "cts",
  display_name: "Hallway",
  room_name: "Hall",
  buffer_depth: 8,
  buffer_capacity: 20,
  pending_flush: null,
  cooldown_remaining_seconds: null,
  rate_per_second: 1,
  tokens_available: 1,
  images_eligible_total: 90,
  images_dropped_total: 10,
  last_event_at: "2026-06-14T12:00:00Z",
};

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  onPageOptions: vi.fn(),
  setFilter: vi.fn(),
  getAggregatorState: vi.fn(),
  getMediaBuffer: vi.fn(),
  notifyError: vi.fn(),
}));

const aggregatorState = reactive({
  items: [camera],
  total: 1,
  loading: false,
  error: null,
  page: 1,
  itemsPerPage: 25,
  filters: { origin: null, query: "", roomName: null },
  autoRefresh: false,
  history: new Map([["camera-1", [{ t: "2026-06-14T12:00:00Z", depth: 8 }]]]),
  roomNames: ["Hall"],
});

vi.mock("@/composables/useAggregatorState.js", () => ({
  AGGREGATOR_REFRESH_SECONDS: 15,
  useAggregatorState: () => ({
    state: aggregatorState,
    actions: {
      fetch: mocks.fetch,
      onPageOptions: mocks.onPageOptions,
      setFilter: mocks.setFilter,
    },
  }),
}));

vi.mock("@/composables/useChartTheme.js", () => ({
  useChartTheme: () => ({ chartTheme: { value: { _severity: {} } } }),
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    snack: { value: false },
    snackText: { value: "" },
    snackColor: { value: "error" },
    notify: { error: mocks.notifyError },
  }),
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getAggregatorState: mocks.getAggregatorState,
    getMediaBuffer: mocks.getMediaBuffer,
  },
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (value) => value || "",
  formatDateTimeFull: (value) => value || "",
}));

vi.mock("@/components/charts/CcQueueDepthChart.vue", () => ({
  default: {
    name: "CcQueueDepthChart",
    props: ["cameras", "theme", "loading"],
    emits: ["select"],
    template:
      '<button data-testid="queue-chart" @click="$emit(\'select\', cameras[0].camera_id)">chart</button>',
  },
}));

vi.mock("@/components/charts/CcTimeSeriesChart.vue", () => ({
  default: {
    name: "CcTimeSeriesChart",
    props: ["series", "unit"],
    template: "<div data-testid='history-chart' />",
  },
}));

vi.mock("@/components/common/CcSegmentedToggle.vue", () => ({
  default: {
    name: "CcSegmentedToggle",
    props: ["modelValue", "options"],
    emits: ["update:modelValue"],
    template:
      "<button data-testid=\"origin-toggle\" @click=\"$emit('update:modelValue', 'cts')\">origin</button>",
  },
}));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: {
    name: "CcMetricTile",
    props: ["label", "value"],
    template: '<div data-testid="metric">{{ label }}:{{ value }}</div>',
  },
}));

import CameraMediaView from "@/views/admin/CameraMediaView.vue";

const stubs = {
  "v-spacer": { template: "<span />" },
  "v-switch": { template: "<div />", props: ["modelValue", "label"] },
  "v-chip": { template: "<span><slot /></span>", props: ["color", "size", "variant"] },
  "v-btn": {
    template: "<button @click=\"$emit('click')\"><slot /></button>",
    props: ["loading", "icon"],
  },
  "v-text-field": { template: "<div />", props: ["modelValue", "placeholder"] },
  "v-select": { template: "<div />", props: ["modelValue", "items", "placeholder"] },
  "v-alert": { template: "<div><slot /></div>", props: ["type"] },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "sm", "lg"] },
  "v-card": { template: "<section><slot /></section>" },
  "v-card-title": { template: "<header><slot /></header>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-data-table-server": {
    name: "VDataTableServer",
    props: ["headers", "items", "itemsLength", "itemsPerPage", "page", "loading"],
    emits: ["click:row", "update:options"],
    template:
      '<button data-testid="camera-table" @click="$emit(\'click:row\', $event, { item: items[0] })"><slot name="no-data" /></button>',
  },
  "v-navigation-drawer": {
    template: "<aside><slot /></aside>",
    props: ["modelValue", "location", "width", "temporary"],
  },
  "v-divider": { template: "<hr />" },
  "v-progress-circular": { template: "<div />" },
  "v-img": {
    template: "<div><slot name='placeholder' /><slot name='error' /></div>",
    props: ["src"],
  },
  "v-icon": { template: "<i><slot /></i>" },
  "v-dialog": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-snackbar": { template: "<div><slot /></div>", props: ["modelValue", "color"] },
};

function mountView() {
  return mount(CameraMediaView, { global: { stubs } });
}

beforeEach(() => {
  mocks.fetch.mockReset();
  mocks.onPageOptions.mockReset();
  mocks.setFilter.mockReset();
  mocks.getAggregatorState.mockReset();
  mocks.getMediaBuffer.mockReset();
  mocks.notifyError.mockReset();
  aggregatorState.items = [camera];
  aggregatorState.total = 1;
  aggregatorState.error = null;
});

describe("CameraMediaView", () => {
  it("renders KPI tiles from aggregator state", () => {
    const wrapper = mountView();

    expect(wrapper.text()).toContain("Cameras:1");
    expect(wrapper.text()).toContain("Buffered frames:8");
    expect(wrapper.text()).toContain("Image-eligible:90");
    expect(wrapper.text()).toContain("Dropped:10");
  });

  it("origin segmented toggle delegates filtering to the composable", async () => {
    const wrapper = mountView();

    await wrapper.find('[data-testid="origin-toggle"]').trigger("click");

    expect(mocks.setFilter).toHaveBeenCalledWith("origin", "cts");
  });

  it("binds server-side pagination state to the table", () => {
    const wrapper = mountView();
    const table = wrapper.findComponent({ name: "VDataTableServer" });

    expect(table.props("itemsLength")).toBe(1);
    expect(table.props("itemsPerPage")).toBe(25);
    expect(table.props("page")).toBe(1);
  });

  it("opens the drill-in drawer from a table row click", async () => {
    const wrapper = mountView();

    await wrapper.find('[data-testid="camera-table"]').trigger("click");

    expect(wrapper.vm.drawerOpen).toBe(true);
    expect(wrapper.vm.selectedCamera.camera_id).toBe("camera-1");
  });

  it("renders chart and table from composable state without a direct aggregator API call", () => {
    const wrapper = mountView();
    const chart = wrapper.findComponent({ name: "CcQueueDepthChart" });
    const table = wrapper.findComponent({ name: "VDataTableServer" });

    expect(chart.props("cameras")[0].camera_id).toBe("camera-1");
    expect(table.props("items")[0].camera_id).toBe("camera-1");
    expect(mocks.getAggregatorState).not.toHaveBeenCalled();
  });
});
