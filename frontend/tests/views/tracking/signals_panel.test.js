/**
 * U4-T4: SignalsPanel
 *
 * Verifies:
 * - Signal counts chart renders via CcBarChart (D2)
 * - No <svg><rect> hand-rolled chart in the migrated code
 * - CcProvenanceBadge is used for source/quality display (D5)
 */
import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ── Mock dependencies ────────────────────────────────────────────────────────

vi.mock("@/services/cts.js", () => ({
  cts: {
    getSignalExplorer: vi.fn().mockResolvedValue({
      rows: [
        {
          id: "s1",
          signal_type: "pacing",
          severity: "warning",
          person_id: "alice",
          room_name: "Hallway",
          source: "observation",
          quality: 0.8,
          fired_at: "2026-05-29T10:00:00Z",
        },
        {
          id: "s2",
          signal_type: "sundowning_index",
          severity: "info",
          person_id: "bob",
          room_name: "Kitchen",
          source: "transition",
          quality: null,
          fired_at: "2026-05-29T09:00:00Z",
        },
      ],
      aggregates: {
        by_kind: { pacing: 3, sundowning_index: 1 },
        by_room: { Hallway: 3, Kitchen: 1 },
      },
    }),
    getSignalEvidence: vi.fn(),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }),
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => `FMT(${iso || ""})`,
}));

vi.mock("@/components/charts/CcBarChart.vue", () => ({
  default: {
    name: "CcBarChart",
    template: '<div data-testid="cc-bar-chart" />',
    props: ["categories", "series", "loading", "height"],
    emits: ["select"],
  },
}));

vi.mock("@/components/dashboard/CcSectionCard.vue", () => ({
  default: { template: "<div><slot /></div>", props: ["title"] },
}));

vi.mock("@/components/dashboard/CcProvenanceBadge.vue", () => ({
  default: {
    template:
      '<span data-testid="provenance-badge" :data-source="source" :data-quality="String(quality)" />',
    props: ["source", "quality"],
  },
}));

import SignalsPanel from "../../../src/views/tracking/panels/SignalsPanel.vue";

const stubs = {
  "v-alert": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-data-table": {
    template: `
      <div data-testid="v-data-table">
        <template v-for="item in (items || [])" :key="item && item.id">
          <slot name="item.source" :item="item" />
          <slot name="item.signal_type" :item="item" />
        </template>
        <slot name="no-data" />
      </div>`,
    props: ["headers", "items", "loading"],
  },
  "v-navigation-drawer": { template: "<div><slot /></div>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "sm", "md"] },
  "v-btn": {
    template: "<button><slot /></button>",
    props: ["size", "variant", "color", "loading"],
  },
  "v-select": { template: "<div />", props: ["modelValue", "items", "label"] },
  "v-progress-linear": { template: "<div />", props: ["modelValue"] },
  "v-progress-circular": { template: "<div />" },
  "v-chip": {
    template: '<span :data-prepend-icon="prependIcon"><slot /></span>',
    props: ["size", "color", "variant", "prependIcon"],
  },
  "v-icon": { template: "<i />" },
  "v-divider": { template: "<hr />" },
  "v-spacer": { template: "<div />" },
};

describe("SignalsPanel", () => {
  it("renders CcBarChart for signal counts — not SVG rect", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    expect(w.find('[data-testid="cc-bar-chart"]').exists()).toBe(true);
  });

  it("kindBars includes pacing and sundowning_index from aggregates", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    expect(w.vm.kindBars.map((b) => b.kind)).toContain("pacing");
    expect(w.vm.kindBars.map((b) => b.kind)).toContain("sundowning_index");
  });

  it("signal table rows show CcProvenanceBadge (D5)", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    expect(w.findAll('[data-testid="provenance-badge"]').length).toBeGreaterThan(0);
  });

  it("signal with null quality passes null to badge (not fabricated)", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    const nullBadge = w
      .findAll('[data-testid="provenance-badge"]')
      .find((b) => b.attributes("data-quality") === "null");
    expect(nullBadge).toBeDefined();
  });

  it("SignalsPanel.vue source has no SVG rect element (D2 compliance)", () => {
    const src = readFileSync(
      resolve(__dirname, "../../../src/views/tracking/panels/SignalsPanel.vue"),
      "utf-8",
    );
    expect(src).not.toMatch(/<rect\b/);
  });

  it("formatTime uses timezone.js formatDateTimeShort (rule 3)", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    expect(w.vm.formatTime("2026-05-29T10:00:00Z")).toBe("FMT(2026-05-29T10:00:00Z)");
  });

  it("signal kind cell renders through the signalKinds registry (generic fallback for pacing)", async () => {
    const w = mount(SignalsPanel, { global: { stubs } });
    await flushPromises();
    // "pacing" is not in SIGNAL_KIND_PRESENTATIONS, so it must still render
    // via the generic fallback (humanized label, default icon), not crash.
    expect(w.text()).toContain("pacing");
    const table = w.find('[data-testid="v-data-table"]');
    expect(table.html()).toContain('data-prepend-icon="mdi-bell-outline"');
  });
});
