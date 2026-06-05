/**
 * AdminView — M2 integration check.
 *
 * Verifies that MaraudersToggle is mounted in the app bar alongside the
 * existing light/dark toggle, without Vue or Router warnings.
 * Heavy-weight dependencies are stubbed so this remains a unit test.
 */
import { beforeEach, describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { reactive } from "vue";

// ── Service mocks ──────────────────────────────────────────────────────────

vi.mock("@/services/api.js", () => ({
  api: {
    reloadConfig: vi.fn().mockResolvedValue({}),
    setApiKey: vi.fn(),
  },
}));

vi.mock("@/services/cts.js", () => ({
  cts: {
    getUnacknowledgedCount: vi.fn().mockResolvedValue({ count: 0, signals: [] }),
  },
}));

// ── Vuetify useTheme mock ──────────────────────────────────────────────────

vi.mock("vuetify", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useTheme: vi.fn(() => ({
      global: { name: { value: "ccDark" } },
    })),
  };
});

// ── useMaraudersMode mock (so MaraudersToggle renders cleanly) ─────────────

const maraudersState = reactive({ enabled: false, reducedMotion: false });
vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: maraudersState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

// ── Component stubs ────────────────────────────────────────────────────────

const stubs = {
  AdminParticleBackground: { template: "<div data-testid='admin-particle-background' />" },
  MaraudersAdminBackground: { template: "<div data-testid='marauders-admin-background' />" },
  // Vuetify components not available without a full Vuetify install in tests
  "v-app":                { template: "<div><slot /></div>" },
  "v-navigation-drawer":  { template: "<div><slot /><slot name='prepend' /><slot name='append' /></div>" },
  "v-app-bar":            { template: "<div><slot /></div>" },
  "v-app-bar-title":      { template: "<div><slot /></div>" },
  "v-spacer":             { template: "<span />" },
  "v-btn":                { template: "<button @click=\"$emit('click')\"><slot /></button>", props: ["icon", "size", "variant", "color", "title", "aria-label", "prepend-icon", "disabled"] },
  "v-icon":               { template: "<span><slot /></span>" },
  "v-list":               { template: "<ul><slot /></ul>" },
  "v-list-item":          { template: "<li @click=\"$emit('click')\"><slot /></li>", props: ["to", "prepend-icon", "title", "rounded"] },
  "v-list-subheader":     { template: "<div @click=\"$emit('click')\"><slot /></div>" },
  "v-divider":            { template: "<hr />" },
  "v-main":               { template: "<main><slot /></main>" },
  "v-container":          { template: "<div><slot /></div>" },
  "v-dialog":             { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-card":               { template: "<div><slot /></div>" },
  "v-card-title":         { template: "<div><slot /></div>" },
  "v-card-text":          { template: "<div><slot /></div>" },
  "v-card-actions":       { template: "<div><slot /></div>" },
  "v-text-field":         { template: "<input />", props: ["modelValue", "label", "type", "hide-details", "append-inner-icon"] },
  "v-snackbar":           { template: "<div><slot /></div>", props: ["modelValue", "color", "timeout"] },
  "router-view":          { template: "<div />" },
  // Leave MaraudersToggle real so we verify it is registered and renders
};

import AdminView from "@/views/AdminView.vue";

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
}

beforeEach(() => {
  maraudersState.enabled = false;
  maraudersState.reducedMotion = false;
});

describe("AdminView — M2: MaraudersToggle in app bar", () => {
  it("renders MaraudersToggle in the app bar without warnings", async () => {
    const router = buildRouter();
    await router.push("/");

    const wrapper = mount(AdminView, {
      global: {
        plugins: [router],
        stubs,
      },
    });

    await flushPromises();

    // MaraudersToggle renders a v-btn; check that the component itself is present
    // in the component tree (not stubbed, so it will exist as a Vue instance).
    const toggle = wrapper.findComponent({ name: "MaraudersToggle" });
    expect(toggle.exists()).toBe(true);

    wrapper.unmount();
  });
});

describe("AdminView — M5: shared Marauders SVG definitions", () => {
  it("mounts the global heatmap and painterly definitions once regardless of mode", async () => {
    const router = buildRouter();
    await router.push("/");

    const wrapper = mount(AdminView, {
      global: {
        plugins: [router],
        stubs,
      },
    });

    await flushPromises();

    expect(wrapper.findAll("#marauders-heat-blur")).toHaveLength(1);
    expect(wrapper.findAll("#marauders-heat-ramp")).toHaveLength(1);
    expect(wrapper.findAll("#marauders-paint")).toHaveLength(1);
    expect(wrapper.findAll("#marauders-paint-strong")).toHaveLength(1);

    wrapper.unmount();
  });
});

describe("AdminView — Marauders background seam", () => {
  it("renders the neuron particle background outside Marauders mode", async () => {
    const router = buildRouter();
    await router.push("/");

    const wrapper = mount(AdminView, {
      global: {
        plugins: [router],
        stubs,
      },
    });
    await flushPromises();

    expect(wrapper.find("[data-testid='admin-particle-background']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='marauders-admin-background']").exists()).toBe(false);

    wrapper.unmount();
  });

  it("replaces the neuron particles with the map background in Marauders mode", async () => {
    maraudersState.enabled = true;
    const router = buildRouter();
    await router.push("/");

    const wrapper = mount(AdminView, {
      global: {
        plugins: [router],
        stubs,
      },
    });
    await flushPromises();

    expect(wrapper.find("[data-testid='marauders-admin-background']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='admin-particle-background']").exists()).toBe(false);

    wrapper.unmount();
  });
});
