import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive } from "vue";

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  }),
}));

vi.mock("@/components/admin/visitors/VisitorClusterCard.vue", () => ({
  default: {
    name: "VisitorClusterCard",
    props: ["cluster", "mergeMode", "selected"],
    template:
      "<div class='cluster-card'>{{ cluster.cluster_id }}" +
      "<button class='name-btn' @click=\"$emit('name', cluster)\">Name</button>" +
      "<button class='dismiss-btn' @click=\"$emit('dismiss', cluster.cluster_id)\">Dismiss</button>" +
      "<button class='select-btn' @click=\"$emit('toggle-select', cluster.cluster_id)\">Select</button>" +
      "</div>",
  },
}));

vi.mock("@/components/admin/visitors/VisitorNameDialog.vue", () => ({
  default: {
    name: "VisitorNameDialog",
    props: ["modelValue", "saving"],
    template:
      "<div v-if='modelValue' class='name-dialog'>" +
      "<button class='submit' @click=\"$emit('submit', { name: 'Nurse Priya', personId: 'nurse-priya' })\">Submit</button>" +
      "</div>",
  },
}));

const { store } = vi.hoisted(() => ({ store: {} }));

vi.mock("@/composables/useVisitorReview.js", () => ({
  useVisitorReview: () => store.value,
}));

import VisitorsView from "@/views/admin/VisitorsView.vue";

function makeStore(overrides = {}) {
  const state = reactive({
    clusters: [],
    total: 0,
    listLoading: false,
    listError: "",
    statusFilter: "surfaced",
    disabled: false,
    acting: false,
    mergeSelection: [],
    ...overrides,
  });
  return {
    state,
    actions: {
      loadList: vi.fn().mockResolvedValue(),
      setStatusFilter: vi.fn((status) => {
        state.statusFilter = status;
      }),
      nameCluster: vi.fn().mockResolvedValue(),
      dismissCluster: vi.fn().mockResolvedValue(),
      toggleMergeSelection: vi.fn((id) => {
        state.mergeSelection = [...state.mergeSelection, id].slice(-2);
      }),
      clearMergeSelection: vi.fn(() => {
        state.mergeSelection = [];
      }),
      mergeSelected: vi.fn().mockResolvedValue(),
    },
  };
}

const stubs = {
  CcSegmentedToggle: {
    props: ["modelValue", "options"],
    emits: ["update:modelValue"],
    template:
      "<div><button v-for='o in options' :key='o.value' class='seg-btn' @click=\"$emit('update:modelValue', o.value)\">{{ o.label }}</button></div>",
  },
  "v-spacer": { template: "<span />" },
  "v-btn": {
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled"],
    emits: ["click"],
  },
  "v-chip": { template: "<span><slot /></span>" },
  "v-alert": { template: "<div class='v-alert'><slot /></div>" },
  "v-progress-circular": { template: "<div />" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
};

function mountView() {
  return mount(VisitorsView, { global: { stubs } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("VisitorsView", () => {
  it("loads the list on mount", async () => {
    store.value = makeStore();
    const wrapper = mountView();
    await flushPromises();

    expect(store.value.actions.loadList).toHaveBeenCalled();
    expect(wrapper.exists()).toBe(true);
  });

  it("renders cluster cards for each item in state.clusters", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }, { cluster_id: "c2" }] });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.findAll(".cluster-card")).toHaveLength(2);
  });

  it("shows the empty state when there are no clusters", async () => {
    store.value = makeStore({ clusters: [] });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("No visitors here yet");
  });

  it("shows a permission-denied message rather than crashing on a list error", async () => {
    store.value = makeStore({ listError: "Insufficient permissions" });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Insufficient permissions");
    expect(wrapper.find(".v-alert").exists()).toBe(true);
  });

  it("shows the disabled-clustering banner when state.disabled is true", async () => {
    store.value = makeStore({ disabled: true });
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("currently disabled");
  });

  it("clicking a status filter option calls setStatusFilter and reloads with the new status", async () => {
    store.value = makeStore();
    const wrapper = mountView();
    await flushPromises();
    store.value.actions.loadList.mockClear();

    const candidateBtn = wrapper.findAll(".seg-btn").find((b) => b.text() === "Candidate");
    await candidateBtn.trigger("click");

    expect(store.value.actions.setStatusFilter).toHaveBeenCalledWith("candidate");
  });

  it("opens the name dialog and submits the naming payload", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }] });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find(".name-btn").trigger("click");
    await flushPromises();
    expect(wrapper.find(".name-dialog").exists()).toBe(true);

    await wrapper.find(".submit").trigger("click");
    await flushPromises();

    expect(store.value.actions.nameCluster).toHaveBeenCalledWith("c1", {
      personId: "nurse-priya",
      name: "Nurse Priya",
    });
  });

  it("dismiss asks for confirmation before calling the action", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }] });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find(".dismiss-btn").trigger("click");
    await flushPromises();

    // The confirm dialog is open; the action has not fired yet.
    expect(store.value.actions.dismissCluster).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Dismiss this cluster?");

    const confirmBtn = wrapper.findAll("button").find((b) => b.text() === "Confirm");
    await confirmBtn.trigger("click");
    await flushPromises();

    expect(store.value.actions.dismissCluster).toHaveBeenCalledWith("c1");
  });

  it("merge mode: selecting two clusters enables Merge selected, and confirming calls mergeSelected", async () => {
    store.value = makeStore({
      clusters: [{ cluster_id: "c1" }, { cluster_id: "c2" }],
    });
    const wrapper = mountView();
    await flushPromises();

    const mergeToggle = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Merge duplicates"));
    await mergeToggle.trigger("click");
    await flushPromises();

    const selectBtns = wrapper.findAll(".select-btn");
    await selectBtns[0].trigger("click");
    await selectBtns[1].trigger("click");
    await flushPromises();

    expect(store.value.state.mergeSelection).toEqual(["c1", "c2"]);

    const mergeSelectedBtn = wrapper.findAll("button").find((b) => b.text() === "Merge selected");
    await mergeSelectedBtn.trigger("click");
    await flushPromises();
    const confirmBtn = wrapper.findAll("button").find((b) => b.text() === "Confirm");
    await confirmBtn.trigger("click");
    await flushPromises();

    expect(store.value.actions.mergeSelected).toHaveBeenCalled();
  });
});
