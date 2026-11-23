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
    getKnowledgeDocument: vi.fn(),
    getLLMModels: vi.fn(),
    replaceQuizQuestions: vi.fn(),
    setQuizQuestionImage: vi.fn(),
    deleteQuizQuestionImage: vi.fn(),
    getVoiceDefaults: vi.fn(),
    suggestQuizVoiceInstruction: vi.fn(),
  },
}));
const { routeMock } = vi.hoisted(() => ({ routeMock: { query: {} } }));

// One mock object behind the api.js barrel and every typed module the views import.
vi.mock("@/services/api.js", () => ({ api: apiMock }));
vi.mock("@/services/modules/quizzes", () => apiMock);
vi.mock("@/services/modules/knowledge", () => apiMock);
vi.mock("@/services/modules/layouts", () => apiMock);
vi.mock("@/services/modules/pipeline", () => apiMock);
vi.mock("vue-router", () => ({ useRoute: () => routeMock }));

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
    props: ["modelValue", "label", "multiple", "clearable", "chips", "closableChips"],
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
  "v-img": { props: ["src"], template: "<img class='v-img-stub' />" },
  "v-file-input": { props: ["modelValue", "label"], template: "<input type='file' />" },
  VoiceInstructionField: {
    name: "VoiceInstructionField",
    props: ["modelValue", "resourceType", "documentId"],
    emits: ["update:modelValue"],
    template: "<div class='voice-field-stub' />",
  },
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
  "v-data-table-server": {
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
    apiMock.getKnowledgeDocument.mockResolvedValue({ id: 5, images: [] });
    apiMock.getVoiceDefaults.mockResolvedValue({ quiz_default: "Ask one question at a time." });
    routeMock.query = {};
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

  it("sends the tag filter as repeated tag parameters", async () => {
    const wrapper = mount(QuizzesView, { global: { stubs } });
    await flushPromises();
    apiMock.getQuizzes.mockClear();

    wrapper.vm.$.setupState.state.filters.tags = ["family", "medication"];
    wrapper.vm.$.setupState.actions.onFilterChange();
    await flushPromises();

    expect(apiMock.getQuizzes).toHaveBeenCalledWith(
      expect.objectContaining({ tag: ["family", "medication"], offset: 0 }),
    );
    expect(apiMock.getQuizzes.mock.calls[0][0]).not.toHaveProperty("tags");
  });

  it("moves a question by sending the complete order, then re-reads the quiz", async () => {
    apiMock.getQuiz.mockResolvedValue({
      id: 10,
      question_layout_id: "quiz_with_optional_image",
      questions: [
        { id: 101, ord: 0, question_type: "open_ended", question_text: "Q1", choices: [] },
        { id: 102, ord: 1, question_type: "open_ended", question_text: "Q2", choices: [] },
      ],
    });
    const wrapper = mount(QuizzesView, { global: { stubs } });
    await flushPromises();
    await wrapper.find(".quiz-row").trigger("click");
    await flushPromises();
    apiMock.getQuiz.mockClear();

    wrapper.findAllComponents(QuizQuestionEditorCard)[1].vm.$emit("move", -1);
    await flushPromises();

    expect(apiMock.reorderQuizQuestions).toHaveBeenCalledWith(10, [
      { id: 102, ord: 0 },
      { id: 101, ord: 1 },
    ]);
    expect(apiMock.getQuiz).toHaveBeenCalledWith(10);
  });

  it("a field save does not re-read the quiz under a caregiver who is still typing", async () => {
    let finishSave;
    apiMock.updateQuizQuestion.mockReturnValue(new Promise((resolve) => (finishSave = resolve)));
    const wrapper = mount(QuizzesView, { global: { stubs } });
    await flushPromises();
    await wrapper.find(".quiz-row").trigger("click");
    await flushPromises();
    apiMock.getQuiz.mockClear();
    const card = wrapper.findComponent(QuizQuestionEditorCard);

    card.vm.$emit("change", { ...card.props("question"), question_text: "Saved text" });
    card.vm.$.setupState.draft.explanation = "Still typing";
    finishSave({});
    await flushPromises();

    expect(apiMock.updateQuizQuestion).toHaveBeenCalledWith(
      10,
      101,
      expect.objectContaining({ question_text: "Saved text" }),
    );
    expect(apiMock.getQuiz).not.toHaveBeenCalled();
    expect(card.vm.$.setupState.draft.explanation).toBe("Still typing");
  });

  it("opens AI generation for a document linked from the document page", async () => {
    routeMock.query = { suggest_doc_id: "5" };
    const wrapper = mount(QuizzesView, { global: { stubs } });
    await flushPromises();

    const suggest = wrapper.findComponent(QuizSuggestDialog);
    expect(suggest.props("modelValue")).toBe(true);
    expect(suggest.props("initialDocumentId")).toBe(5);
  });
});

describe("QuizQuestionEditorCard choice ids", () => {
  it("gives each added choice the next free letter, never null", async () => {
    const wrapper = mount(QuizQuestionEditorCard, {
      props: {
        question: {
          id: 1,
          question_type: "multiple_choice",
          question_text: "Q",
          choices: [
            { id: "a", text: "x" },
            { id: "b", text: "y" },
          ],
        },
      },
      global: { stubs },
    });

    const add = wrapper.find("[data-test='add-choice']");
    await add.trigger("click");
    await add.trigger("click");

    const updates = wrapper.emitted("update:question");
    expect(updates.at(-1)[0].choices.map((c) => c.id)).toEqual(["a", "b", "c", "d"]);
  });
});

describe("QuizFormDialog saving", () => {
  const quiz = {
    id: 10,
    title: "Family",
    question_layout_id: "quiz_with_optional_image",
    tags: [],
    voice_instruction: "",
    questions: [
      { id: 101, ord: 0, question_type: "open_ended", question_text: "Q1", choices: [] },
      { id: 102, ord: 1, question_type: "open_ended", question_text: "Q2", choices: [] },
    ],
  };

  it("saves an edited quiz's details and whole ordered list in one call", async () => {
    apiMock.updateQuiz.mockResolvedValue({});
    const wrapper = mount(QuizFormDialog, {
      props: { modelValue: true, mode: "edit", quiz },
      global: { stubs },
    });
    await flushPromises();

    const cards = wrapper.findAllComponents(QuizQuestionEditorCard);
    cards[1].vm.$emit("move", -1);
    cards[0].vm.$emit("delete");
    await flushPromises();
    wrapper.findComponent({ name: "AppDialog" }).vm.$emit("confirm");
    await flushPromises();

    // Details and questions travel together: a failed list can no longer leave a new
    // title saved over the old questions.
    expect(apiMock.updateQuiz).toHaveBeenCalledTimes(1);
    const [quizId, body] = apiMock.updateQuiz.mock.calls[0];
    expect(quizId).toBe(10);
    expect(body.title).toBe("Family");
    expect(body.questions.map((q) => q.id)).toEqual([101]);
    expect(apiMock.replaceQuizQuestions).not.toHaveBeenCalled();
    expect(apiMock.deleteQuizQuestion).not.toHaveBeenCalled();
    expect(apiMock.createQuizQuestion).not.toHaveBeenCalled();
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("creates a quiz together with its questions, with normalized choice ids", async () => {
    apiMock.createQuiz.mockResolvedValue({ id: 11 });
    const wrapper = mount(QuizFormDialog, {
      props: { modelValue: true, mode: "create" },
      global: { stubs },
    });
    await flushPromises();
    wrapper.vm.applySuggestion({
      document_id: 5,
      suggestion: {
        title: "Drafted",
        questions: [
          {
            question_type: "multiple_choice",
            question_text: "Who?",
            choices: [{ text: "Priya", is_correct: true }, { text: "Ravi" }],
          },
        ],
      },
    });
    wrapper.vm.$.setupState.form.question_layout_id = "quiz_with_optional_image";
    wrapper.findComponent({ name: "AppDialog" }).vm.$emit("confirm");
    await flushPromises();

    expect(apiMock.createQuiz).toHaveBeenCalledTimes(1);
    const body = apiMock.createQuiz.mock.calls[0][0];
    expect(body.questions[0].choices.map((c) => c.id)).toEqual(["a", "b"]);
    expect(apiMock.createQuizQuestion).not.toHaveBeenCalled();
  });
});
