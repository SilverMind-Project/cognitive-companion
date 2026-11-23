import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { companionStubs } from "./companionStubs.js";

const listeners = {};
vi.mock("@/services/WebSocketClient.js", () => ({
  wsClient: {
    on: vi.fn((event, cb) => {
      listeners[event] = cb;
    }),
    off: vi.fn((event) => {
      delete listeners[event];
    }),
    _sendJson: vi.fn(),
  },
}));

const { wsClient } = await import("@/services/WebSocketClient.js");
const QuizDialog = (await import("@/components/companion/QuizDialog.vue")).default;

async function emit(payload) {
  listeners.onStatus(payload);
  await nextTick();
}

const question = (ord, extra = {}) => ({
  type: "quiz_question",
  session_id: 7,
  question_ord: ord,
  question_type: "multiple_choice",
  question_text: ord === 0 ? "Who is Priya?" : "Where is Boston?",
  choices: [
    { id: "a", text: "Granddaughter" },
    { id: "b", text: "Neighbour" },
  ],
  hint: ord === 0 ? "Priya lives in Boston." : "",
  ...extra,
});

function start(extra = {}) {
  return emit({
    type: "quiz_start",
    session_id: 7,
    title: "Family",
    intro_voice_text: "Shall we chat?",
    total_questions: 2,
    interaction_mode: "gentle",
    voice: true,
    ...extra,
  });
}

function find(wrapper, testId) {
  return wrapper.find(`[data-test="${testId}"]`);
}

describe("QuizDialog", () => {
  let wrapper;

  beforeEach(() => {
    vi.useFakeTimers();
    wrapper = mount(QuizDialog, { global: { stubs: companionStubs } });
  });

  afterEach(() => {
    wrapper.unmount();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("shows question 1 as soon as a voice quiz sends it, with no Start gate", async () => {
    await start();
    expect(find(wrapper, "quiz-start").exists()).toBe(true);

    await emit(question(0));

    expect(find(wrapper, "question-text").text()).toBe("Who is Priya?");
  });

  it("leaves the intro on its own when the senior does not tap", async () => {
    await start({ voice: false });
    await emit(question(0));
    expect(find(wrapper, "quiz-start").exists()).toBe(true);

    vi.advanceTimersByTime(3000);
    await nextTick();

    expect(find(wrapper, "question-text").text()).toBe("Who is Priya?");
  });

  it("gentle mode offers a hint and answers a different choice with a warm reminder", async () => {
    await start();
    await emit(question(0));

    await find(wrapper, "quiz-hint").trigger("click");
    expect(find(wrapper, "quiz-hint-text").text()).toContain("Priya lives in Boston.");

    await find(wrapper, "quiz-choice-b").trigger("click");
    expect(wsClient._sendJson).toHaveBeenCalledWith(
      expect.objectContaining({ type: "quiz_answer", question_ord: 0, choice_id: "b" }),
    );
    await emit({
      type: "quiz_answer_recorded",
      session_id: 7,
      question_ord: 0,
      is_correct: false,
      explanation: "Priya is your granddaughter.",
      advance: true,
    });

    const feedback = find(wrapper, "quiz-feedback");
    expect(feedback.text()).toContain("Good thought! Here is a little reminder:");
    expect(feedback.text()).toContain("Priya is your granddaughter.");
    expect(feedback.classes()).toContain("feedback-bar--reminder");
    expect(feedback.text()).not.toMatch(/not quite|incorrect|wrong/i);
    expect(find(wrapper, "quiz-choice-b").attributes("data-color")).toBe("primary");
  });

  it("gentle mode closes with thanks and no score", async () => {
    await start();
    await emit(question(0));
    await emit({ type: "quiz_complete", session_id: 7, num_correct: 0, num_answered: 2 });

    expect(find(wrapper, "quiz-complete-gentle").exists()).toBe(true);
    expect(find(wrapper, "quiz-score").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("0 / 2");
  });

  it("standard mode shows right/not-quite feedback and the score", async () => {
    await start({ interaction_mode: "standard" });
    await emit(question(0));
    expect(find(wrapper, "quiz-hint").exists()).toBe(false);

    await find(wrapper, "quiz-choice-b").trigger("click");
    await emit({
      type: "quiz_answer_recorded",
      session_id: 7,
      question_ord: 0,
      is_correct: false,
      explanation: "",
      advance: false,
    });
    expect(find(wrapper, "quiz-feedback").text()).toContain("Not quite.");

    await emit({ type: "quiz_complete", session_id: 7, num_correct: 1, num_answered: 2 });
    vi.advanceTimersByTime(1500);
    await nextTick();
    expect(find(wrapper, "quiz-score").text()).toContain("1 / 2");
  });

  it("closes when the session times out", async () => {
    await start();
    await emit(question(0));

    await emit({ type: "quiz_timeout", session_id: 7 });

    expect(wrapper.find(".dialog-open").exists()).toBe(false);
  });

  it("ignores messages for another quiz session", async () => {
    await start();
    await emit(question(0));

    await emit({ type: "quiz_timeout", session_id: 99 });

    expect(wrapper.find(".dialog-open").exists()).toBe(true);
  });

  it("advances to the next question after the feedback dwell", async () => {
    await start();
    await emit(question(0));
    await find(wrapper, "quiz-choice-a").trigger("click");
    await emit({
      type: "quiz_answer_recorded",
      session_id: 7,
      question_ord: 0,
      is_correct: true,
      explanation: "",
      advance: true,
    });
    expect(find(wrapper, "quiz-feedback").text()).toContain("Wonderful!");
    await emit(question(1));

    vi.advanceTimersByTime(1500);
    await nextTick();

    expect(find(wrapper, "question-text").text()).toBe("Where is Boston?");
  });

  it("stops listening when unmounted", () => {
    wrapper.unmount();
    expect(wsClient.off).toHaveBeenCalledWith("onStatus", expect.any(Function));
    wrapper = mount(QuizDialog, { global: { stubs: companionStubs } });
  });
});
