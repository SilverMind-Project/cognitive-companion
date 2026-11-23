import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import KnowledgeAnswerWidget from "@/components/companion/KnowledgeAnswerWidget.vue";
import { companionStubs } from "./companionStubs.js";

function mountWidget(props = {}) {
  return mount(KnowledgeAnswerWidget, {
    props: { queryText: "", answerText: "", serverTimestamp: "", ...props },
    global: { stubs: companionStubs },
  });
}

async function deliver(wrapper, ts = "2026-11-22T10:00:00Z") {
  await wrapper.setProps({
    queryText: "When is lunch?",
    answerText: "At noon.",
    serverTimestamp: ts,
  });
}

describe("KnowledgeAnswerWidget", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("closes on its own after 45 seconds", async () => {
    const wrapper = mountWidget();
    await deliver(wrapper);
    expect(wrapper.find(".dialog-open").exists()).toBe(true);

    await vi.advanceTimersByTimeAsync(44000);
    expect(wrapper.find(".dialog-open").exists()).toBe(true);
    await vi.advanceTimersByTimeAsync(1000);

    expect(wrapper.find(".dialog-open").exists()).toBe(false);
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("shows the time left draining", async () => {
    const wrapper = mountWidget();
    await deliver(wrapper);

    await vi.advanceTimersByTimeAsync(9000);

    const progress = wrapper.find('[data-test="knowledge-answer-countdown"]');
    expect(Number(progress.attributes("data-value"))).toBeCloseTo(80, 0);
  });

  it("'Got it' closes at once and the timer does not fire later", async () => {
    const wrapper = mountWidget();
    await deliver(wrapper);

    await wrapper.find('[data-test="knowledge-answer-dismiss"]').trigger("click");
    await vi.advanceTimersByTimeAsync(60000);

    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("a new answer restarts the countdown", async () => {
    const wrapper = mountWidget();
    await deliver(wrapper, "t1");
    await vi.advanceTimersByTimeAsync(40000);

    await deliver(wrapper, "t2");
    await vi.advanceTimersByTimeAsync(40000);

    expect(wrapper.find(".dialog-open").exists()).toBe(true);
  });

  it("stays until dismissed when auto-dismiss is off", async () => {
    const wrapper = mountWidget({ dismissAfterSeconds: 0 });
    await deliver(wrapper);

    await vi.advanceTimersByTimeAsync(120000);

    expect(wrapper.find(".dialog-open").exists()).toBe(true);
    expect(wrapper.find('[data-test="knowledge-answer-countdown"]').exists()).toBe(false);
  });
});
