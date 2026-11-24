import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import GuidedTaskWidget from "@/components/companion/GuidedTaskWidget.vue";
import { companionStubs } from "./companionStubs.js";

const STATE = {
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

function mountWidget(props = {}) {
  return mount(GuidedTaskWidget, {
    props: { session: STATE, ...props },
    global: { stubs: companionStubs },
  });
}

describe("GuidedTaskWidget", () => {
  it("shows the current step, its progress, and emits each tap", async () => {
    const wrapper = mountWidget();

    expect(wrapper.find("[data-test=guided-progress]").text()).toBe("Step 2 of 4");
    expect(wrapper.find("[data-test=guided-prompt]").text()).toBe("Fill the kettle with water.");
    await wrapper.find("[data-test=guided-done]").trigger("click");
    await wrapper.find("[data-test=guided-repeat]").trigger("click");
    await wrapper.find("[data-test=guided-help-button]").trigger("click");

    expect(wrapper.emitted("action")).toEqual([["done"], ["repeat"], ["help"]]);
    expect(wrapper.find("[data-test=guided-help]").exists()).toBe(false);
  });

  it("reassures her when a caregiver is called, without technical detail", () => {
    const wrapper = mountWidget({ session: { ...STATE, status: "escalated" } });

    const banner = wrapper.find("[data-test=guided-help]").text();
    expect(banner).toContain("Help is on the way");
    const text = wrapper.text();
    for (const jargon of ["escalated", "session", "12", "/admin", "caregiver_takeover"]) {
      expect(text).not.toContain(jargon);
    }
  });

  it("leaves finishing a step to the caregiver during a takeover", () => {
    const wrapper = mountWidget({ session: { ...STATE, status: "caregiver_takeover" } });

    expect(wrapper.find("[data-test=guided-done]").exists()).toBe(false);
    expect(wrapper.find("[data-test=guided-repeat]").exists()).toBe(true);
    expect(wrapper.find("[data-test=guided-help]").exists()).toBe(true);
  });

  it("disables every button while a tap is waiting for its answer", () => {
    const wrapper = mountWidget({ pendingAction: "repeat" });

    for (const id of ["guided-done", "guided-repeat", "guided-help-button"]) {
      expect(wrapper.find(`[data-test=${id}]`).attributes("disabled")).toBeDefined();
    }
  });

  it("celebrates a finished routine and hides when nothing is running", () => {
    const done = mountWidget({ session: { ...STATE, status: "completed" }, celebrating: true });
    expect(done.find("[data-test=guided-celebrate]").text()).toContain("Morning Tea");
    expect(done.find("[data-test=guided-done]").exists()).toBe(false);

    expect(mountWidget({ session: null }).find("[data-test=guided-task-widget]").exists()).toBe(
      false,
    );
    const summoning = mountWidget({ session: { ...STATE, status: "summoning" } });
    expect(summoning.find("[data-test=guided-task-widget]").exists()).toBe(false);
  });
});
