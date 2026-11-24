import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import GuidedTaskWidget from "@/components/companion/GuidedTaskWidget.vue";
import { TV_MODE_CLASS, useTvNavigation } from "@/composables/useTvNavigation.js";
import { companionStubs } from "../components/companion/companionStubs.js";

const listeners = {};
vi.mock("@/services/WebSocketClient.js", () => ({
  wsClient: {
    on: vi.fn((event, cb) => {
      listeners[event] = cb;
    }),
    off: vi.fn(),
    _sendJson: vi.fn(),
  },
}));

const { wsClient } = await import("@/services/WebSocketClient.js");
const QuizDialog = (await import("@/components/companion/QuizDialog.vue")).default;

// The real Vuetify overlay structure: dialogs render outside the companion root.
const overlayStubs = {
  ...companionStubs,
  "v-dialog": {
    props: ["modelValue"],
    template:
      '<div v-if="modelValue" class="v-overlay v-overlay--active"><div class="v-overlay__content"><slot /></div></div>',
  },
};

const STEP = {
  type: "guided_session_state",
  session_id: 12,
  routine_id: 3,
  routine_name: "Morning Tea",
  person_id: "resident-1",
  status: "waiting",
  current_step_ord: 1,
  total_steps: 4,
  prompt_text: "Fill the kettle with water.",
  at: "2026-11-24T09:00:00Z",
};

function press(key) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  document.dispatchEvent(event);
  return event;
}

const mounted = [];
function attach(component, options) {
  const wrapper = mount(component, { attachTo: document.body, ...options });
  mounted.push(wrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.documentElement.classList.remove(TV_MODE_CLASS);
  vi.clearAllMocks();
});

describe("useTvNavigation", () => {
  it("dpad arrow keys and enter select quiz choices and guided actions in tv mode", async () => {
    const widget = attach(GuidedTaskWidget, {
      props: { session: STEP },
      global: { stubs: companionStubs },
    });
    const tv = useTvNavigation({
      route: { query: { surface_kind: "tv" } },
      root: () => widget.element,
    });
    tv.actions.mount();
    expect(document.documentElement.classList.contains(TV_MODE_CLASS)).toBe(true);

    // First press focuses the first control; Right moves on; Enter selects it.
    press("ArrowRight");
    expect(document.activeElement?.getAttribute("data-test")).toBe("guided-done");
    press("ArrowRight");
    const enter = press("Enter");
    expect(enter.defaultPrevented).toBe(true);
    expect(widget.emitted("action")).toEqual([["repeat"]]);

    // A quiz dialog opens on top: the remote now moves within the dialog only.
    const quiz = attach(QuizDialog, { global: { stubs: overlayStubs } });
    listeners.onStatus({
      type: "quiz_start",
      session_id: 7,
      title: "Family",
      intro_voice_text: "",
      total_questions: 1,
      interaction_mode: "gentle",
      voice: true,
    });
    listeners.onStatus({
      type: "quiz_question",
      session_id: 7,
      question_ord: 0,
      question_type: "multiple_choice",
      question_text: "Who is Priya?",
      choices: [
        { id: "a", text: "Granddaughter" },
        { id: "b", text: "Neighbour" },
      ],
      hint: "",
    });
    await nextTick();

    const choiceB = quiz.find('[data-test="quiz-choice-b"]').element;
    choiceB.focus();
    press("ArrowLeft");
    expect(document.activeElement?.getAttribute("data-test")).toBe("quiz-choice-a");
    press("Enter");
    expect(wsClient._sendJson).toHaveBeenCalledWith(
      expect.objectContaining({ type: "quiz_answer", question_ord: 0, choice_id: "a" }),
    );
    expect(widget.emitted("action")).toEqual([["repeat"]]);
    tv.actions.unmount();
  });

  it("stops at the ends instead of wrapping", () => {
    const widget = attach(GuidedTaskWidget, {
      props: { session: STEP },
      global: { stubs: companionStubs },
    });
    const tv = useTvNavigation({ deviceIsTelevision: () => true, root: () => widget.element });
    tv.actions.mount();

    press("ArrowDown");
    press("ArrowUp");
    press("ArrowUp");

    expect(document.activeElement?.getAttribute("data-test")).toBe("guided-done");
    tv.actions.unmount();
  });

  it("leaves keys alone off a TV and removes its class on unmount", () => {
    const widget = attach(GuidedTaskWidget, {
      props: { session: STEP },
      global: { stubs: companionStubs },
    });
    const tv = useTvNavigation({ root: () => widget.element });
    tv.actions.mount();

    const event = press("ArrowDown");

    expect(event.defaultPrevented).toBe(false);
    expect(document.documentElement.classList.contains(TV_MODE_CLASS)).toBe(false);
    tv.actions.unmount();
  });
});
