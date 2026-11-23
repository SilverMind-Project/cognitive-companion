import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, shallowMount } from "@vue/test-utils";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getInfoCards: vi.fn(),
    getInfoCard: vi.fn(),
    updateInfoCard: vi.fn(),
    createInfoCard: vi.fn(),
    suggestInfoCard: vi.fn(),
    getKnowledgeDocument: vi.fn(),
    getKnowledgeDocuments: vi.fn(),
    getKnowledgeLayouts: vi.fn(),
    getLLMModels: vi.fn(),
  },
}));

vi.mock("@/services/modules/info_cards", () => apiMock);
vi.mock("@/services/modules/knowledge", () => apiMock);
vi.mock("@/services/modules/layouts", () => apiMock);
vi.mock("@/services/modules/pipeline", () => apiMock);
vi.mock("@/services/modules/quizzes", () => apiMock);
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }),
  requireNotify: vi.fn(),
}));

const InfoCardsView = (await import("@/views/admin/InfoCardsView.vue")).default;
const InfoCardFormDialog = (await import("@/components/knowledge/InfoCardFormDialog.vue")).default;

const fullCard = {
  id: 3,
  title: "Lunch",
  body_text: "Lunch is at 12:30 in the kitchen.",
  layout_id: "card_text_only",
  document_id: null,
  tags: ["routine"],
  voice_instruction: "Say it warmly.",
  image_slots: [],
};

describe("InfoCardsView edit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getInfoCards.mockResolvedValue({ items: [], total: 0 });
    apiMock.getKnowledgeDocuments.mockResolvedValue({ items: [], total: 0 });
    apiMock.getKnowledgeLayouts.mockResolvedValue({ layouts: [] });
    apiMock.getLLMModels.mockResolvedValue([]);
  });

  it("opens the editor with the full card, so saving keeps the card's text", async () => {
    apiMock.getInfoCard.mockResolvedValue(fullCard);
    const wrapper = shallowMount(InfoCardsView);
    await flushPromises();

    // A list row: InfoCardListOut has no body_text.
    await wrapper.vm.$.setupState.editCard({ id: 3, title: "Lunch", tags: ["routine"] });
    await flushPromises();

    expect(apiMock.getInfoCard).toHaveBeenCalledWith(3);
    const dialog = wrapper.findComponent(InfoCardFormDialog);
    expect(dialog.props("modelValue")).toBe(true);
    expect(dialog.props("mode")).toBe("edit");
    expect(dialog.props("card").body_text).toBe("Lunch is at 12:30 in the kitchen.");
  });

  it("does not open the editor when the card cannot be loaded", async () => {
    apiMock.getInfoCard.mockRejectedValue(new Error("offline"));
    const wrapper = shallowMount(InfoCardsView);
    await flushPromises();

    await wrapper.vm.$.setupState.editCard({ id: 3, title: "Lunch" });
    await flushPromises();

    expect(wrapper.findComponent(InfoCardFormDialog).props("modelValue")).toBe(false);
  });
});

describe("InfoCardFormDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fills the edit form from the card and saves its text and voice instruction", async () => {
    apiMock.updateInfoCard.mockResolvedValue({});
    const wrapper = shallowMount(InfoCardFormDialog, {
      props: { modelValue: true, mode: "edit", card: fullCard },
    });
    await flushPromises();

    expect(wrapper.vm.form.body_text).toBe("Lunch is at 12:30 in the kitchen.");
    wrapper.vm.form.title = "Lunch time";
    wrapper.findComponent({ name: "AppDialog" }).vm.$emit("confirm");
    await flushPromises();

    expect(apiMock.updateInfoCard).toHaveBeenCalledWith(
      3,
      expect.objectContaining({
        title: "Lunch time",
        body_text: "Lunch is at 12:30 in the kitchen.",
        voice_instruction: "Say it warmly.",
      }),
    );
    expect(wrapper.emitted("saved")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue").at(-1)).toEqual([false]);
  });

  it("starts a new card from the linked document and keeps a typed voice instruction", async () => {
    apiMock.suggestInfoCard.mockResolvedValue({
      title: "Drafted",
      body_text: "Drafted body.",
      voice_instruction: "Drafted tone.",
    });
    const wrapper = shallowMount(InfoCardFormDialog, {
      props: { modelValue: true, mode: "create", initialDocumentId: 5 },
    });
    await flushPromises();
    expect(wrapper.vm.form.document_id).toBe(5);

    wrapper.vm.form.voice_instruction = "Typed tone.";
    await wrapper.vm.$.setupState.generate();

    expect(apiMock.suggestInfoCard).toHaveBeenCalledWith(5, undefined);
    expect(wrapper.vm.form.body_text).toBe("Drafted body.");
    expect(wrapper.vm.form.voice_instruction).toBe("Typed tone.");
  });
});
