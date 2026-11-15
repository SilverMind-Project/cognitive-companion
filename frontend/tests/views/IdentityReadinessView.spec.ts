import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import { computed, reactive } from "vue";

vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v: string) => v }));

const { store } = vi.hoisted(() => ({ store: { value: undefined as unknown } }));
vi.mock("@/composables/useIdentityReadiness", () => ({
  useIdentityReadiness: () => store.value,
}));

import IdentityReadinessView from "@/views/admin/IdentityReadinessView.vue";

function step(key: string, state: string, next_action: string, optional = false) {
  return { key, state, detail: `${key} detail`, next_action, optional };
}

const TODAY = {
  steps: [
    step("roster", "blocked", "enroll_members"),
    step("ingest", "ready", "none"),
    step("floor_frame", "blocked", "upload_floor_plan"),
    step("capture", "blocked", "enable_capture"),
    step("labeling", "blocked", "enable_capture"),
    step("artifact", "blocked", "fit_and_deploy_artifact"),
    step("face_policy", "attention", "fit_and_deploy_artifact"),
    step("templates", "blocked", "fit_and_deploy_artifact", true),
    step("body_gallery", "unknown", "check_service"),
  ],
  blocking_step: "roster",
  review_queues: [
    { surface: "visitors", waiting: 84 },
    { surface: "face_calibration", waiting: 0 },
    { surface: "reid_review", waiting: null },
  ],
  checked_at: "2026-11-14T09:00:00Z",
};

function makeStore(readiness: unknown = TODAY, extra: Record<string, unknown> = {}) {
  const state = reactive({ readiness, loading: false, error: "", forbidden: false, ...extra });
  return { state, stepByKey: computed(() => ({})), actions: { load: vi.fn() } };
}

const stubs = {
  RouterLink: RouterLinkStub,
  "v-spacer": { template: "<span />" },
  "v-btn": { template: "<button :data-to='to'><slot /></button>", props: ["to", "loading"] },
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-progress-circular": { template: "<div />" },
  "v-card": { template: "<div><slot /></div>" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot name='prepend' /><slot /><slot name='append' /></li>" },
  "v-list-item-title": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>", props: ["color"] },
};

function mountView() {
  return mount(IdentityReadinessView, { global: { stubs } });
}

type Store = ReturnType<typeof makeStore>;

beforeEach(() => {
  store.value = makeStore();
});

describe("IdentityReadinessView", () => {
  it("loads on mount and names the blocking step", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect((store.value as Store).actions.load).toHaveBeenCalledTimes(1);
    expect(wrapper.get("[data-test='blocking-summary']").text()).toContain("Enroll everyone");
    expect(wrapper.get("[data-test='step-roster']").find("[data-test='start-here']").exists()).toBe(
      true,
    );
    expect(wrapper.findAll("[data-test='start-here']")).toHaveLength(1);
  });

  it("puts the prerequisites before the chain and numbers the chain links", async () => {
    const wrapper = mountView();
    await flushPromises();
    const keys = wrapper
      .findAll("[data-test^='step-']")
      .map((w) => w.attributes("data-test")?.replace("step-", ""));
    expect(keys.slice(0, 2)).toEqual(["ingest", "floor_frame"]);
    expect(wrapper.get("[data-test='step-labeling']").text()).toContain("3");
    expect(wrapper.get("[data-test='step-body_gallery']").text()).toContain("6-8");
  });

  it("shows every server state with its label", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.get("[data-test='state-ingest']").text()).toBe("Ready");
    expect(wrapper.get("[data-test='state-face_policy']").text()).toBe("Needs attention");
    expect(wrapper.get("[data-test='state-roster']").text()).toBe("Blocked");
    expect(wrapper.get("[data-test='state-body_gallery']").text()).toBe("Unknown");
  });

  it("links an in-app action and words a configuration change without a link", async () => {
    const wrapper = mountView();
    await flushPromises();
    const enroll = wrapper.get("[data-test='action-roster']");
    expect(enroll.text()).toContain("enroll every person");
    expect(enroll.attributes("data-to")).toBe("/admin/persons");
    expect(wrapper.get("[data-test='action-capture']").text()).toContain(
      "calibration_capture.enabled",
    );
    expect(wrapper.find("[data-test='action-ingest']").exists()).toBe(false);
  });

  it("lists every review queue with its waiting count and a link", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.get("[data-test='waiting-visitors']").text()).toBe("84 waiting");
    expect(wrapper.get("[data-test='waiting-face_calibration']").text()).toBe("Nothing waiting");
    // An unreadable owner is never shown as an empty queue.
    expect(wrapper.get("[data-test='waiting-reid_review']").text()).toBe("Count unavailable");
    expect(wrapper.get("[data-test='open-visitors']").attributes("data-to")).toBe(
      "/admin/visitors",
    );
    expect(wrapper.get("[data-test='open-reid_review']").attributes("data-to")).toBe(
      "/admin/cts/reid-review",
    );
  });

  it("has no blocking summary when nothing is blocked", async () => {
    store.value = makeStore({ ...TODAY, blocking_step: null });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find("[data-test='blocking-summary']").exists()).toBe(false);
    expect(wrapper.find("[data-test='start-here']").exists()).toBe(false);
  });

  it("shows a load error with retry", async () => {
    store.value = makeStore(null, { error: "Service unavailable" });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.get("[data-test='load-error']").text()).toContain("Service unavailable");
    expect(wrapper.find("[data-test='step-roster']").exists()).toBe(false);
  });

  it("shows the forbidden state without any steps", async () => {
    store.value = makeStore(TODAY, { forbidden: true });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find("[data-test='forbidden']").exists()).toBe(true);
    expect(wrapper.find("[data-test='step-roster']").exists()).toBe(false);
  });
});
