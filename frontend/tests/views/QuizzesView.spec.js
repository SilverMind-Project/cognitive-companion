import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getQuizzes: vi.fn(),
    getQuiz: vi.fn(),
    createQuiz: vi.fn(),
    updateQuiz: vi.fn(),
    deleteQuiz: vi.fn(),
    approveQuiz: vi.fn(),
    archiveQuiz: vi.fn(),
    restoreQuiz: vi.fn(),
    createQuizQuestion: vi.fn(),
    updateQuizQuestion: vi.fn(),
    deleteQuizQuestion: vi.fn(),
    reorderQuizQuestions: vi.fn(),
    suggestQuiz: vi.fn(),
    regenerateQuizQuestion: vi.fn(),
    getKnowledgeLayouts: vi.fn(),
    getKnowledgeDocuments: vi.fn(),
    getLLMModels: vi.fn(),
  },
}));

// One mock object behind the api.js barrel and every typed module the views import.
vi.mock("@/services/api.js", () => ({ api: apiMock }));
vi.mock("@/services/modules/quizzes", () => apiMock);
vi.mock("@/services/modules/knowledge", () => apiMock);
vi.mock("@/services/modules/layouts", () => apiMock);
vi.mock("@/services/modules/pipeline", () => apiMock);

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    notify: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }),
  requireNotify: vi.fn(),
}));

import QuizzesView from "@/views/admin/QuizzesView.vue";
import QuizQuestionEditorCard from "@/components/knowledge/QuizQuestionEditorCard.vue";
import QuizFormDialog from "@/components/knowledge/QuizFormDialog.vue";
import QuizSuggestDialog from "@/components/knowledge/QuizSuggestDialog.vue";

const stubs = {
  AppDialog: {
    name: "AppDialog",
    props: [
      "modelValue",
      "section",
      "size",
      "persistent",
      "icon",
      "label",
      "title",
      "sections",
      "hint",
      "confirmLabel",
      "confirmLoading",
      "confirmDisabled",
      "confirmColor",
    ],
    emits: ["update:modelValue", "update:section", "confirm", "cancel"],
    template: `
      <div v-if="modelValue" class="app-dialog-stub" :data-title="title" :data-label="label">
        <slot />
        <slot name="section-generate" />
        <slot name="section-details" />
        <slot name="section-questions" />
        <slot name="footerActions" />
      </div>
    `,
  },
  LlmModelPicker: {
    name: "LlmModelPicker",
    props: ["modelValue", "modelItems", "label", "hint", "persistentHint", "clearable"],
    emits: ["update:modelValue"],
    template: "<div class='llm-model-picker-stub' />",
  },
  "v-spacer": { template: "<span />" },
  "v-select": {
    props: ["modelValue", "items", "label", "itemTitle", "itemValue", "clearable", "rules"],
    emits: ["update:modelValue"],
    template: "<div class='v-select-stub' />",
  },
  "v-combobox": {
    props: ["modelValue", "label", "multiple", "clearable", "chips", "deletableChips"],
    emits: ["update:modelValue"],
    template: "<div class='v-combobox-stub' />",
  },
  "v-btn": {
    props: ["color", "variant", "prependIcon", "size", "icon", "disabled", "loading", "block"],
    emits: ["click"],
    template: "<button :disabled='disabled' @click=\"$emit('click', $event)\"><slot /></button>",
  },
  "v-card": {
    props: ["variant", "rounded", "flat"],
    template: "<div class='v-card-stub'><slot /></div>",
  },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-chip": {
    props: ["size", "color", "variant"],
    template: "<span class='v-chip-stub'><slot /></span>",
  },
  "v-divider": { template: "<hr />" },
  "v-row": { props: ["dense", "align"], template: "<div class='v-row-stub'><slot /></div>" },
  "v-col": { props: ["cols", "sm"], template: "<div class='v-col-stub'><slot /></div>" },
  "v-radio-group": {
    props: ["modelValue", "inline", "density", "hideDetails"],
    emits: ["update:modelValue"],
    template: "<div class='v-radio-group-stub'><slot /></div>",
  },
  "v-radio": { props: ["label", "value"], template: "<span class='v-radio-stub' />" },
  "v-textarea": {
    props: ["modelValue", "label", "rows", "density", "hideDetails"],
    emits: ["update:modelValue", "change"],
    template: "<textarea class='v-textarea-stub' />",
  },
  "v-text-field": {
    props: ["modelValue", "label", "type", "min", "max", "density", "hideDetails", "rules"],
    emits: ["update:modelValue", "change"],
    template: "<input class='v-text-field-stub' />",
  },
  "v-checkbox": {
    props: ["modelValue", "label", "density", "hideDetails"],
    emits: ["update:modelValue", "change"],
    template: "<input type='checkbox' class='v-checkbox-stub' />",
  },
  "v-dialog": {
    props: ["modelValue", "maxWidth", "persistent"],
    template: "<div v-if='modelValue' class='v-dialog-stub'><slot /></div>",
  },
  "v-data-table": {
    props: [
      "headers",
      "items",
      "loading",
      "itemsLength",
      "itemsPerPage",
      "page",
      "showExpand",
      "itemValue",
    ],
    emits: ["update:options", "click:row"],
    template: `
      <div class="v-data-table-stub">
        <div
          v-for="item in items"
          :key="item.id"
          class="quiz-row"
          @click="$emit('click:row', $event, { item })"
        >
          <span class="quiz-title">{{ item.title }}</span>
          <slot name="item.actions" :item="item" />
          <slot name="expanded-row" :item="item" />
        </div>
        <slot v-if="!items.length" name="no-data" />
      </div>
    `,
  },
};

describe("QuizzesView.vue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());

    apiMock.getQuizzes.mockResolvedValue({
      items: [
        {
          id: 10,
          title: "Morning Reminiscence",
          question_layout_id: "quiz_with_optional_image",
          status: "draft",
          version: 1,
          question_count: 1,
        },
      ],
      total: 1,
    });
    apiMock.getQuiz.mockResolvedValue({
      id: 10,
      title: "Morning Reminiscence",
      question_layout_id: "quiz_with_optional_image",
      status: "draft",
      version: 1,
      questions: [
        {
          id: 101,
          quiz_id: 10,
          ord: 0,
          question_type: "multiple_choice",
          question_text: "Where does Priya live?",
          choices: [{ id: "a", text: "Boston", is_correct: true }],
          expected_answer: "",
          explanation: "She lives in Boston.",
        },
      ],
    });
    apiMock.getKnowledgeLayouts.mockResolvedValue({
      layouts: [{ id: "quiz_with_optional_image", display_name: "Quiz with Image" }],
    });
    apiMock.getKnowledgeDocuments.mockResolvedValue({ items: [], total: 0 });
    apiMock.getLLMModels.mockResolvedValue([]);
  });

  it("renders quiz list, expands a row to render QuizQuestionEditorCard, and opens QuizFormDialog and QuizSuggestDialog", async () => {
    const wrapper = mount(QuizzesView, {
      global: { stubs },
    });
    await flushPromises();

    expect(apiMock.getQuizzes).toHaveBeenCalled();
    expect(wrapper.text()).toContain("Morning Reminiscence");

    // Expand row to load quiz detail and render QuizQuestionEditorCard
    await wrapper.find(".quiz-row").trigger("click");
    await flushPromises();

    expect(apiMock.getQuiz).toHaveBeenCalledWith(10);
    const questionCards = wrapper.findAllComponents(QuizQuestionEditorCard);
    expect(questionCards.length).toBeGreaterThanOrEqual(1);

    // Open New Quiz dialog (QuizFormDialog)
    const buttons = wrapper.findAll("button");
    const newQuizBtn = buttons.find((b) => b.text().includes("New Quiz"));
    expect(newQuizBtn).toBeDefined();
    await newQuizBtn.trigger("click");
    await flushPromises();

    const formDialog = wrapper.findComponent(QuizFormDialog);
    expect(formDialog.exists()).toBe(true);
    expect(formDialog.props("modelValue")).toBe(true);

    // Open Generate with AI dialog (QuizSuggestDialog)
    const suggestBtn = buttons.find((b) => b.text().includes("Generate with AI"));
    expect(suggestBtn).toBeDefined();
    await suggestBtn.trigger("click");
    await flushPromises();

    const suggestDialog = wrapper.findComponent(QuizSuggestDialog);
    expect(suggestDialog.exists()).toBe(true);
    expect(suggestDialog.props("modelValue")).toBe(true);
  });
});
