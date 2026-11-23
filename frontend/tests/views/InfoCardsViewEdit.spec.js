import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, shallowMount } from "@vue/test-utils";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getInfoCards: vi.fn(),
    getInfoCard: vi.fn(),
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

describe("InfoCardsView edit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.getInfoCards.mockResolvedValue({ items: [], total: 0 });
    apiMock.getKnowledgeDocuments.mockResolvedValue({ items: [], total: 0 });
    apiMock.getKnowledgeLayouts.mockResolvedValue({ layouts: [] });
    apiMock.getLLMModels.mockResolvedValue([]);
  });

  it("fills the editor from the full card, so saving keeps the card's text", async () => {
    apiMock.getInfoCard.mockResolvedValue({
      id: 3,
      title: "Lunch",
      body_text: "Lunch is at 12:30 in the kitchen.",
      layout_id: "card_text_only",
      document_id: null,
      tags: ["routine"],
      image_slots: [],
    });
    const wrapper = shallowMount(InfoCardsView);
    await flushPromises();

    // A list row: InfoCardListOut has no body_text.
    await wrapper.vm.$.setupState.editCard({ id: 3, title: "Lunch", tags: ["routine"] });

    expect(apiMock.getInfoCard).toHaveBeenCalledWith(3);
    expect(wrapper.vm.$.setupState.editForm.body_text).toBe("Lunch is at 12:30 in the kitchen.");
  });

  it("does not open the editor when the card cannot be loaded", async () => {
    apiMock.getInfoCard.mockRejectedValue(new Error("offline"));
    const wrapper = shallowMount(InfoCardsView);
    await flushPromises();

    await wrapper.vm.$.setupState.editCard({ id: 3, title: "Lunch" });

    expect(wrapper.vm.$.setupState.editingItem).toBeNull();
  });
});
