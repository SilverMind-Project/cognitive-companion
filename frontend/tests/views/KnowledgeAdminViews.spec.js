import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const { apiMock, routeMock, routerMock, confirmMock } = vi.hoisted(() => ({
  apiMock: {
    getKnowledgeDocument: vi.fn(),
    updateKnowledgeDocument: vi.fn(),
    addKnowledgeDocumentImage: vi.fn(),
    deleteKnowledgeDocumentImage: vi.fn(),
    approveKnowledgeDocument: vi.fn(),
    archiveKnowledgeDocument: vi.fn(),
    restoreKnowledgeDocument: vi.fn(),
    deleteKnowledgeDocument: vi.fn(),
    reembedKnowledgeDocument: vi.fn(),
    getTagAnalytics: vi.fn(),
    getSeniorKnowledgeQueries: vi.fn(),
    getQuizSessions: vi.fn(),
    getQuizSession: vi.fn(),
    getInfoCardDeliveries: vi.fn(),
  },
  routeMock: { params: { id: "7" }, query: {} },
  routerMock: { push: vi.fn() },
  confirmMock: vi.fn(),
}));

vi.mock("@/services/modules/knowledge", () => apiMock);
vi.mock("@/services/modules/interactions", () => apiMock);
vi.mock("vue-router", () => ({ useRoute: () => routeMock, useRouter: () => routerMock }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }),
  requireNotify: vi.fn(),
}));
vi.mock("@/composables/useConfirm.js", () => ({
  useConfirm: () => ({
    confirmDialog: false,
    confirmTitle: "",
    confirmText: "",
    confirmLabel: "",
    cancelLabel: "",
    confirmColor: "",
    require: confirmMock,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }),
}));

const KnowledgeDocumentEditView = (await import("@/views/admin/KnowledgeDocumentEditView.vue"))
  .default;
const KnowledgeInteractionsView = (await import("@/views/admin/KnowledgeInteractionsView.vue"))
  .default;

const passthrough = { template: "<div><slot /></div>" };
const btn = {
  props: ["disabled", "loading", "color"],
  emits: ["click"],
  template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
};
const editStubs = {
  "v-btn": btn,
  "v-card": passthrough,
  "v-card-text": passthrough,
  "v-card-title": passthrough,
  "v-row": passthrough,
  "v-col": passthrough,
  "v-chip": passthrough,
  "v-spacer": { template: "<span />" },
  "v-divider": { template: "<hr />" },
  "v-img": { template: "<img />" },
  "v-text-field": { props: ["modelValue"], template: "<input />" },
  "v-textarea": { props: ["modelValue"], template: "<textarea />" },
  "v-combobox": { props: ["modelValue", "closableChips"], template: "<div />" },
  "v-file-input": { props: ["modelValue"], template: "<input type='file' />" },
  "v-progress-circular": { template: "<span />" },
  "v-dialog": { props: ["modelValue"], template: "<div v-if='modelValue'><slot /></div>" },
  "v-card-actions": passthrough,
  ArchiveOrDeleteDialog: { props: ["modelValue"], template: "<div />" },
};

const doc = {
  id: 7,
  title: "Family facts",
  source_text: "Priya lives in Boston.",
  tags: ["family"],
  status: "approved",
  images: [{ id: 3, alt_text: "Priya", presigned_url: "http://x/3" }],
};

describe("KnowledgeDocumentEditView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getKnowledgeDocument.mockResolvedValue(doc);
  });

  function mountEdit() {
    return mount(KnowledgeDocumentEditView, { global: { stubs: editStubs } });
  }

  function button(wrapper, testId) {
    return wrapper.find(`[data-test='${testId}']`);
  }

  it("Re-embed calls the API (it was a stub toast) and reloads the document", async () => {
    apiMock.reembedKnowledgeDocument.mockResolvedValue({ ...doc, status: "approved" });
    const wrapper = mountEdit();
    await flushPromises();
    apiMock.getKnowledgeDocument.mockClear();

    await button(wrapper, "reembed").trigger("click");
    await flushPromises();

    expect(apiMock.reembedKnowledgeDocument).toHaveBeenCalledWith(7);
    expect(apiMock.getKnowledgeDocument).toHaveBeenCalledWith(7);
  });

  it("deletes an image with both the document id and the image id", async () => {
    confirmMock.mockResolvedValue(true);
    const wrapper = mountEdit();
    await flushPromises();

    await wrapper.vm.$.setupState.confirmDeleteImage(doc.images[0]);
    await flushPromises();

    expect(apiMock.deleteKnowledgeDocumentImage).toHaveBeenCalledWith(7, 3);
  });

  it("opens card and quiz generation for this document by route name", async () => {
    const wrapper = mountEdit();
    await flushPromises();

    await button(wrapper, "create-card").trigger("click");
    await button(wrapper, "create-quiz").trigger("click");

    expect(routerMock.push).toHaveBeenNthCalledWith(1, {
      name: "admin-info-cards",
      query: { suggest_doc_id: "7" },
    });
    expect(routerMock.push).toHaveBeenNthCalledWith(2, {
      name: "admin-quizzes",
      query: { suggest_doc_id: "7" },
    });
  });
});

const tableStub = {
  name: "v-data-table-server",
  props: ["headers", "items", "itemsLength", "itemsPerPage", "page", "loading", "showExpand"],
  emits: ["update:options", "update:expanded"],
  template: `<div class="table-stub">
    <div v-for="item in items" :key="item.id" class="row">
      <slot v-for="h in headers" :name="'item.' + h.key" :item="item">{{ item[h.key] }}</slot>
      <slot name="expanded-row" :item="item" :columns="headers" />
    </div>
  </div>`,
};
const interactionStubs = {
  "v-tabs": passthrough,
  "v-tab": { props: ["value"], template: "<button><slot /></button>" },
  "v-window": passthrough,
  "v-window-item": passthrough,
  "v-card": passthrough,
  "v-row": passthrough,
  "v-col": passthrough,
  "v-btn": btn,
  "v-chip": { props: ["color"], template: "<span :data-color='color'><slot /></span>" },
  "v-text-field": {
    props: ["modelValue"],
    emits: ["update:modelValue"],
    template: "<input />",
  },
  "v-progress-circular": { template: "<span />" },
  "v-data-table-server": tableStub,
  "v-data-table": { ...tableStub, name: "v-data-table" },
  CcBarChart: { props: ["categories", "series"], template: "<div class='chart' />" },
};

describe("KnowledgeInteractionsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getSeniorKnowledgeQueries.mockResolvedValue({ items: [], total: 0 });
    apiMock.getQuizSessions.mockResolvedValue({
      items: [{ id: 4, quiz_id: 1, status: "completed", started_at: "2026-11-23T10:00:00Z" }],
      total: 31,
    });
    apiMock.getInfoCardDeliveries.mockResolvedValue({ items: [], total: 0 });
  });

  function mountView() {
    return mount(KnowledgeInteractionsView, { global: { stubs: interactionStubs } });
  }

  it("sends date_from/date_to and pages through the server", async () => {
    const wrapper = mountView();
    await flushPromises();
    apiMock.getSeniorKnowledgeQueries.mockClear();
    const { state, actions } = wrapper.vm.$.setupState;

    state.queries.dateFrom = "2026-11-01";
    state.queries.dateTo = "2026-11-22";
    actions.applyDates("queries");
    await flushPromises();
    actions.onOptions("queries", { page: 2, itemsPerPage: 15 });
    await flushPromises();

    expect(apiMock.getSeniorKnowledgeQueries).toHaveBeenNthCalledWith(1, {
      limit: 15,
      offset: 0,
      date_from: "2026-11-01",
      date_to: "2026-11-22",
    });
    expect(apiMock.getSeniorKnowledgeQueries).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 15 }),
    );
    const sessionsTable = wrapper.findAllComponents(tableStub)[1];
    expect(sessionsTable.props("itemsLength")).toBe(31);
  });

  it("renders the recorded answer, latency, and an ungraded answer as Not graded", async () => {
    apiMock.getQuizSession.mockResolvedValue({
      id: 4,
      responses: [
        {
          id: 1,
          question_text: "Who?",
          chosen_choice_text: "Priya",
          is_correct: true,
          latency_ms: 4200,
          channel: "pwa",
        },
        {
          id: 2,
          question_text: "Lunch?",
          open_ended_text: "noon",
          is_correct: null,
          latency_ms: 800,
          channel: "voice",
        },
      ],
    });
    const wrapper = mountView();
    await flushPromises();

    wrapper.findAllComponents(tableStub)[1].vm.$emit("update:expanded", [4]);
    await flushPromises();

    const responses = wrapper.findAll("[data-test='session-response']");
    expect(responses[0].text()).toContain("Priya");
    expect(responses[0].text()).toContain("4.2 s");
    expect(responses[0].text()).toContain("Correct");
    expect(responses[1].text()).toContain("noon");
    expect(responses[1].text()).toContain("800 ms");
    expect(responses[1].text()).toContain("Not graded");
    expect(responses[1].text()).not.toContain("Incorrect");
  });

  it("Tag Analytics loads on first open and charts only tags with graded answers", async () => {
    apiMock.getTagAnalytics.mockResolvedValue({
      tags: [
        { tag: "family", document_count: 2, quiz_count: 1, avg_quiz_score_pct: 66.7 },
        { tag: "garden", document_count: 1, quiz_count: 0, avg_quiz_score_pct: null },
      ],
    });
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.$.setupState.activeTab = "analytics";
    await flushPromises();

    expect(apiMock.getTagAnalytics).toHaveBeenCalledTimes(1);
    const chart = wrapper.findComponent(interactionStubs.CcBarChart);
    expect(chart.props("categories")).toEqual(["family"]);
    expect(chart.props("series")[0].values).toEqual([66.7]);
    expect(wrapper.find("[data-test='analytics-table']").exists()).toBe(true);
  });
});
