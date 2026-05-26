import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

// ── Mocks ──────────────────────────────────────────────────────────────────

const mockNotify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({
    snack: ref(false),
    snackText: ref(""),
    snackColor: ref(""),
    notify: mockNotify,
  }),
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getPersons: vi.fn().mockResolvedValue([]),
    getEnrolledPersons: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("@/composables/useCtsSeverity", () => ({
  severityColor: vi.fn(() => "primary"),
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTime: vi.fn((v) => v || ""),
}));

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));

vi.mock("@/components/cts/keyframes/KeyframeAnnotationDialog.vue", () => ({
  default: {
    name: "KeyframeAnnotationDialog",
    template: '<div class="mock-keyframe-dialog"><slot /></div>',
    props: ["modelValue", "imageUrl", "keyframeId", "identities"],
    emits: ["update:model-value", "saved", "error"],
  },
}));

vi.mock("@/components/common/DialogHeader.vue", () => ({
  default: { template: "<div />", props: ["icon", "label", "title"] },
}));

vi.mock("@/components/common/DialogFooter.vue", () => ({
  default: { template: "<div />", props: ["hint", "confirmLabel", "confirmLoading", "confirmDisabled"] },
}));

vi.mock("@/components/cts/BlurToggle.vue", () => ({
  default: { template: "<div />" },
}));

// Mock cts with vi.hoisted to avoid the hoisting error.
const { mockGetKeyframes } = vi.hoisted(() => ({
  mockGetKeyframes: vi.fn().mockResolvedValue({ keyframes: [] }),
}));

vi.mock("@/services/cts", () => ({
  cts: {
    getKeyframes: mockGetKeyframes,
    getKeyframeBboxes: vi.fn().mockResolvedValue([]),
    getIdentities: vi.fn().mockResolvedValue({ identities: [] }),
    getIdentityHealth: vi.fn().mockResolvedValue({ issues: [], gallery_size: 0 }),
    retainKeyframe: vi.fn().mockResolvedValue({}),
    enrollBatch: vi.fn().mockResolvedValue({ results: [] }),
    enrollFromTracklet: vi.fn().mockResolvedValue({ enrolled_count: 1, identity_id: "p1" }),
    overrideBbox: vi.fn().mockResolvedValue({}),
    applyBboxCorrection: vi.fn().mockResolvedValue({}),
    deleteBbox: vi.fn().mockResolvedValue(null),
  },
}));

// Stub Vuetify components.
const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /></li>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-alert": { template: "<div v-if=\"$attrs.type !== 'hidden'\"><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-snackbar": { template: "<div><slot /></div>" },
  "v-overlay": { template: "<div><slot /></div>" },
  "v-img": { template: "<img />" },
  "v-progress-circular": { template: "<div />" },
  "v-select": { template: "<select><slot /></select>" },
  "v-autocomplete": { template: "<input />" },
  "v-text-field": { template: "<input />" },
  "v-checkbox-btn": { template: "<input type='checkbox' />" },
};

import CTSKeyframesView from "../../src/views/admin/CTSKeyframesView.vue";

async function mountView() {
  const wrapper = mount(CTSKeyframesView, {
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

describe("CTSKeyframesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("re-fetches keyframes after annotation saved event", async () => {
    const wrapper = await mountView();
    const initialCalls = mockGetKeyframes.mock.calls.length;

    const dialog = wrapper.findComponent({ name: "KeyframeAnnotationDialog" });
    expect(dialog.exists()).toBe(true);

    await dialog.vm.$emit("saved");
    await flushPromises();

    expect(mockGetKeyframes).toHaveBeenCalledTimes(initialCalls + 1);
  });

  it("propagates error events from the annotation dialog", async () => {
    const wrapper = await mountView();

    const dialog = wrapper.findComponent({ name: "KeyframeAnnotationDialog" });
    await dialog.vm.$emit("error", "Something went wrong");
    await flushPromises();

    expect(mockNotify.error).toHaveBeenCalledWith("Something went wrong");
  });
});
