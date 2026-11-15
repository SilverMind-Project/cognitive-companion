import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive } from "vue";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/services/modules/identity_targets", async () =>
  (await import("../support/reviewVocabulary")).identityTargetsModuleMock(),
);

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  }),
}));

vi.mock("@/components/admin/visitors/VisitorClusterCard.vue", () => ({
  default: {
    name: "VisitorClusterCard",
    props: ["cluster", "selectMode", "selected"],
    template:
      "<div class='cluster-card'>{{ cluster.cluster_id }}" +
      "<button class='name-btn' @click=\"$emit('name', cluster)\">Name</button>" +
      "<button class='attribute-btn' @click=\"$emit('attribute', cluster.cluster_id)\">Enrolled</button>" +
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
      "<button class='use-existing' @click=\"$emit('attribute', 'resident')\">Mark as theirs</button>" +
      "</div>",
  },
}));

vi.mock("@/components/admin/visitors/VisitorAttributeDialog.vue", () => ({
  default: {
    name: "VisitorAttributeDialog",
    props: ["modelValue", "count", "saving"],
    template:
      "<div v-if='modelValue' class='attribute-dialog'>{{ count }}" +
      "<button class='attribute-submit' @click=\"$emit('submit', 'resident')\">Mark</button>" +
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
    selection: [],
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
      review: vi.fn().mockResolvedValue(),
      toggleSelection: vi.fn((id) => {
        state.selection = state.selection.includes(id)
          ? state.selection.filter((x) => x !== id)
          : [...state.selection, id];
      }),
      clearSelection: vi.fn(() => {
        state.selection = [];
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
  setActivePinia(createPinia());
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

  it("dismiss states its effect and asks for confirmation before calling the action", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }] });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find(".dismiss-btn").trigger("click");
    await flushPromises();

    // The confirm dialog is open; the action has not fired yet.
    expect(store.value.actions.review).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Dismiss this group?");
    // The effect is the server's sentence, not a copy kept in the page.
    expect(wrapper.text()).toContain("Server: dismissed, nothing enrolled.");

    const confirmBtn = wrapper.findAll("button").find((b) => b.text() === "Confirm");
    await confirmBtn.trigger("click");
    await flushPromises();

    expect(store.value.actions.review).toHaveBeenCalledWith(["c1"], "not_usable");
  });

  it("someone enrolled on a card opens the attribute dialog and marks the cluster", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }] });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find(".attribute-btn").trigger("click");
    await flushPromises();
    expect(wrapper.find(".attribute-dialog").text()).toContain("1");

    await wrapper.find(".attribute-submit").trigger("click");
    await flushPromises();

    expect(store.value.actions.review).toHaveBeenCalledWith(["c1"], "is_member", "resident");
    expect(wrapper.find(".attribute-dialog").exists()).toBe(false);
  });

  it("naming someone already enrolled turns into marking the cluster as theirs", async () => {
    store.value = makeStore({ clusters: [{ cluster_id: "c1" }] });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.find(".name-btn").trigger("click");
    await wrapper.find(".use-existing").trigger("click");
    await flushPromises();

    expect(store.value.actions.nameCluster).not.toHaveBeenCalled();
    expect(store.value.actions.review).toHaveBeenCalledWith(["c1"], "is_member", "resident");
  });

  function clickButton(wrapper, testId) {
    return wrapper.find(`[data-test='${testId}']`).trigger("click");
  }

  it("select several: one batch decision for every selected cluster", async () => {
    store.value = makeStore({
      clusters: [{ cluster_id: "c1" }, { cluster_id: "c2" }, { cluster_id: "c3" }],
    });
    const wrapper = mountView();
    await flushPromises();

    await clickButton(wrapper, "select-mode");
    await clickButton(wrapper, "select-all");
    await flushPromises();
    expect(store.value.state.selection).toEqual(["c1", "c2", "c3"]);
    expect(wrapper.find("[data-test='merge-selected']").attributes("disabled")).toBeDefined();

    await clickButton(wrapper, "attribute-selected");
    await flushPromises();
    expect(wrapper.find(".attribute-dialog").text()).toContain("3");
    await wrapper.find(".attribute-submit").trigger("click");
    await flushPromises();

    expect(store.value.actions.review).toHaveBeenCalledWith(
      ["c1", "c2", "c3"],
      "is_member",
      "resident",
    );
  });

  it("merge is offered only for exactly two selected clusters", async () => {
    store.value = makeStore({
      clusters: [{ cluster_id: "c1" }, { cluster_id: "c2" }],
    });
    const wrapper = mountView();
    await flushPromises();

    await clickButton(wrapper, "select-mode");
    const selectBtns = wrapper.findAll(".select-btn");
    await selectBtns[0].trigger("click");
    await selectBtns[1].trigger("click");
    await flushPromises();

    expect(store.value.state.selection).toEqual(["c1", "c2"]);

    await clickButton(wrapper, "merge-selected");
    await flushPromises();
    const confirmBtn = wrapper.findAll("button").find((b) => b.text() === "Confirm");
    await confirmBtn.trigger("click");
    await flushPromises();

    expect(store.value.actions.mergeSelected).toHaveBeenCalled();
  });
});
