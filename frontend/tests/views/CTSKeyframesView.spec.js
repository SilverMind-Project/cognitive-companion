import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const mockNotify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({ notify: mockNotify }),
}));
vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v) => v || "" }));
vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));
vi.mock("@/components/cts/BlurToggle.vue", () => ({ default: { template: "<div />" } }));
vi.mock("@/components/common/DialogHeader.vue", () => ({
  default: { template: "<div />", props: ["icon", "label", "title"] },
}));
vi.mock("@/components/cts/keyframes/KeyframeAnnotationDialog.vue", () => ({
  default: {
    name: "KeyframeAnnotationDialog",
    template: "<div class='mock-annot' />",
    props: ["modelValue", "imageUrl", "keyframeId", "identities"],
    emits: ["update:model-value", "saved", "error"],
  },
}));
vi.mock("@/components/cts/identity/IdentityBboxOverlay.vue", () => ({
  default: {
    name: "IdentityBboxOverlay",
    props: ["imageUrl", "bboxes", "targets", "frameWidth", "frameHeight"],
    emits: ["select"],
    template: `<div class='mock-overlay'>
      <button v-for='b in bboxes' :key='b.ph_id' class='ov-box'
        @click="$emit('select', b)">{{ b.effective_identity_id || 'Unknown' }}</button>
    </div>`,
  },
}));
vi.mock("@/components/cts/identity/IdentityEvidenceBadges.vue", () => ({
  default: {
    name: "IdentityEvidenceBadges",
    template: "<div class='mock-badges' />",
    props: ["bbox", "targets", "detailed"],
  },
}));
vi.mock("@/components/cts/identity/IdentityCorrectionWorkflow.vue", () => ({
  default: {
    name: "IdentityCorrectionWorkflow",
    template: "<div class='mock-workflow' />",
    props: [
      "phId",
      "frameCapturedAt",
      "reviewedFrameId",
      "reviewedBbox",
      "bbox",
      "sourceView",
      "defaultScope",
    ],
    emits: ["applied", "close"],
  },
}));

const { mockGetKeyframes, mockGetCorrectionTargets } = vi.hoisted(() => ({
  mockGetKeyframes: vi.fn(),
  mockGetCorrectionTargets: vi.fn(),
}));

vi.mock("@/services/cts", () => ({
  cts: {
    getKeyframes: mockGetKeyframes,
    getCorrectionTargets: mockGetCorrectionTargets,
  },
}));

const CARD = {
  physical_frame_id: "pf-1",
  camera_id: "kitchen",
  captured_at: "2026-06-20T12:00:00Z",
  image_url: "img.jpg",
  frame_width: 1920,
  frame_height: 1080,
  triggers: [{ keyframe_id: "kf-1", ph_id: "ph-a", tag_reason: "periodic" }],
  trigger_reasons: ["periodic"],
  identity_summary: [
    { effective_identity_id: "amma", count: 1, source_badges: ["ArcFace"] },
    { effective_identity_id: "grandma", count: 1, source_badges: ["ReID"] },
  ],
  unknown_count: 0,
  conflict_count: 0,
  pending_review_count: 0,
  bboxes: [
    {
      bbox_id: "b1",
      ph_id: "ph-a",
      effective_identity_id: "amma",
      x1: 0,
      y1: 0,
      x2: 10,
      y2: 10,
      frame_width: 1920,
      frame_height: 1080,
    },
    {
      bbox_id: "b2",
      ph_id: "ph-b",
      effective_identity_id: "grandma",
      x1: 5,
      y1: 5,
      x2: 15,
      y2: 15,
      frame_width: 1920,
      frame_height: 1080,
    },
  ],
};

const stubs = {
  "v-btn": {
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled", "variant", "color", "size", "prependIcon"],
  },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-chip": {
    template: "<span class='v-chip'><slot /></span>",
    props: ["color", "size", "variant"],
  },
  "v-tooltip": { template: "<span><slot /></span>" },
  "v-divider": { template: "<hr />" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-overlay": { template: "<div><slot /></div>" },
  "v-img": { template: "<div><slot /></div>", props: ["src"] },
  "v-progress-circular": { template: "<div />" },
  "v-pagination": { template: "<div class='pager' />", props: ["modelValue", "length"] },
  "v-select": { template: "<select><slot /></select>", props: ["modelValue", "items"] },
};

import CTSKeyframesView from "@/views/admin/CTSKeyframesView.vue";

async function mountView() {
  const wrapper = mount(CTSKeyframesView, { global: { stubs } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetKeyframes.mockResolvedValue({ keyframes: [CARD], total: 1, truncated: false });
  mockGetCorrectionTargets.mockResolvedValue({
    targets: [
      { identity_id: "amma", display_name: "Amma" },
      { identity_id: "grandma", display_name: "Grandma" },
    ],
    gallery_available: true,
  });
});

describe("CTSKeyframesView", () => {
  it("loads keyframes on mount with server pagination params", async () => {
    await mountView();
    expect(mockGetKeyframes).toHaveBeenCalled();
    const params = mockGetKeyframes.mock.calls[0][0];
    expect(params.limit).toBe(50);
    expect(params.offset).toBe(0);
  });

  it("renders the server card summary with both identities", async () => {
    const w = await mountView();
    expect(w.text()).toContain("Amma");
    expect(w.text()).toContain("Grandma");
  });

  it("filter change resets to the first page and uses server params", async () => {
    const w = await mountView();
    mockGetKeyframes.mockClear();
    // Toggle the conflicts filter (a server-side filter).
    const conflictsBtn = w.findAll("button").find((b) => b.text() === "Conflicts");
    await conflictsBtn.trigger("click");
    await flushPromises();
    const params = mockGetKeyframes.mock.calls[0][0];
    expect(params.conflict_only).toBe(true);
    expect(params.offset).toBe(0);
  });

  it("inspect opens the detail overlay; clicking a box opens the correction workflow", async () => {
    const w = await mountView();
    const inspect = w.findAll("button").find((b) => b.text().includes("Inspect"));
    await inspect.trigger("click");
    await flushPromises();

    // Both bboxes appear in the overlay.
    const boxes = w.findAll(".ov-box");
    expect(boxes).toHaveLength(2);

    // Clicking a box selects it and mounts the shared workflow.
    await boxes[0].trigger("click");
    await flushPromises();
    expect(w.findComponent({ name: "IdentityCorrectionWorkflow" }).exists()).toBe(true);
  });

  it("reloads after a geometry save and surfaces dialog errors", async () => {
    const w = await mountView();
    const dialog = w.findComponent({ name: "KeyframeAnnotationDialog" });
    const before = mockGetKeyframes.mock.calls.length;
    await dialog.vm.$emit("saved");
    await flushPromises();
    expect(mockGetKeyframes.mock.calls.length).toBe(before + 1);

    await dialog.vm.$emit("error", "boom");
    expect(mockNotify.error).toHaveBeenCalledWith("boom");
  });
});
