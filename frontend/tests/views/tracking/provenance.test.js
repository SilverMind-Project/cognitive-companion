/**
 * U4-T7: Provenance display (D5)
 *
 * Verifies:
 * - OverviewPanel renders CcProvenanceBadge on every presence tile
 * - source and quality from PersonLocationEnvelope flow through to the badge
 * - null quality passes null to CcProvenanceBadge (never fabricated — D5)
 * - SignalsPanel renders CcProvenanceBadge on signal rows (source + quality)
 */
import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

// ── Top-level mocks ───────────────────────────────────────────────────────────

vi.mock("@/services/cts.js", () => ({
  cts: {
    getSignalSummary: vi.fn().mockResolvedValue({ by_type: {} }),
    getSignalExplorer: vi.fn().mockResolvedValue({
      rows: [
        { id: "s1", signal_type: "pacing",           severity: "warning", person_id: "alice", room_name: "Hallway", source: "observation", quality: 0.8,  fired_at: "2026-05-29T10:00:00Z" },
        { id: "s2", signal_type: "sundowning_index", severity: "info",    person_id: "bob",   room_name: "Kitchen", source: "transition",  quality: null, fired_at: "2026-05-29T09:00:00Z" },
      ],
      aggregates: { by_kind: { pacing: 1 }, by_room: {} },
    }),
  },
}));

vi.mock("@/composables/useCtsSeverity.js", () => ({ severityColor: () => "grey" }));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { error: vi.fn(), success: vi.fn() } }),
}));

vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: (iso) => iso,
}));

vi.mock("@/components/charts/CcBarChart.vue", () => ({
  default: { template: '<div />', props: ["categories", "series", "loading", "height"] },
}));

vi.mock("@/components/dashboard/CcSectionCard.vue", () => ({
  default: { template: '<div><slot /></div>', props: ["title"] },
}));

vi.mock("@/views/admin/CTSPersonHypothesesView.vue", () => ({
  default: { template: '<div data-testid="ph-view" />' },
}));

vi.mock("@/components/dashboard/CcProvenanceBadge.vue", () => ({
  default: {
    name: "CcProvenanceBadge",
    template: '<span data-testid="provenance-badge" :data-source="source" :data-quality="String(quality)" />',
    props: ["source", "quality"],
  },
}));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: {
    name: "CcMetricTile",
    template: '<div :data-person="label" :data-room="value"><slot name="sparkline" /></div>',
    props: ["label", "value", "status", "to"],
  },
}));

import OverviewPanel from "../../../src/views/tracking/panels/OverviewPanel.vue";
import SignalsPanel  from "../../../src/views/tracking/panels/SignalsPanel.vue";

const sharedStubs = {
  "v-row":    { template: '<div><slot /></div>' },
  "v-col":    { template: '<div><slot /></div>', props: ["cols", "sm", "md"] },
  "v-alert":  { template: '<div><slot /></div>' },
  "v-skeleton-loader": { template: '<div />' },
  "v-chip":   { template: '<span><slot /></span>', props: ["size", "color", "variant"] },
  "v-icon":   { template: '<i />' },
  "v-divider":{ template: '<hr />' },
  "router-link": { template: '<a><slot /></a>' },
  "v-card":   { template: '<div><slot /></div>' },
  "v-card-title": { template: '<div><slot /></div>' },
  "v-card-text":  { template: '<div><slot /></div>' },
  "v-data-table": {
    template: `
      <div data-testid="v-data-table">
        <slot v-for="item in (items || [])" name="item.source" :item="item" />
      </div>`,
    props: ["headers", "items", "loading"],
  },
  "v-navigation-drawer": { template: '<div />' },
  "v-btn": { template: '<button><slot /></button>', props: ["size", "variant", "color", "loading"] },
  "v-select": { template: '<div />', props: ["modelValue", "items"] },
  "v-progress-linear": { template: '<div />' },
  "v-progress-circular": { template: '<div />' },
  "v-spacer":  { template: '<div />' },
  "v-card-actions": { template: '<div />' },
};

const LOCATIONS = [
  { person_id: "alice", display_name: "Alice", room_name: "Kitchen",  source: "observation", quality: 0.95, staleness_seconds: 0,  is_inferred: false },
  { person_id: "bob",   display_name: "Bob",   room_name: "Bathroom", source: "transition",  quality: null, staleness_seconds: 10, is_inferred: true  },
];

describe("OverviewPanel provenance (D5)", () => {
  it("renders CcProvenanceBadge for each presence tile", () => {
    const w = mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs: sharedStubs },
    });
    const badges = w.findAll('[data-testid="provenance-badge"]');
    expect(badges.length).toBeGreaterThanOrEqual(LOCATIONS.length);
  });

  it("Alice's badge has source='observation' and quality='0.95'", () => {
    const w = mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs: sharedStubs },
    });
    const obsBadge = w.findAll('[data-testid="provenance-badge"]').find(
      (b) => b.attributes("data-source") === "observation"
    );
    expect(obsBadge).toBeDefined();
    expect(obsBadge.attributes("data-quality")).toBe("0.95");
  });

  it("Bob's badge passes null quality — never fabricated (D5)", () => {
    const w = mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs: sharedStubs },
    });
    const nullBadge = w.findAll('[data-testid="provenance-badge"]').find(
      (b) => b.attributes("data-quality") === "null"
    );
    expect(nullBadge).toBeDefined();
  });
});

describe("SignalsPanel provenance (D5)", () => {
  it("renders CcProvenanceBadge in signal rows", async () => {
    const w = mount(SignalsPanel, { global: { stubs: sharedStubs } });
    await flushPromises();
    const badges = w.findAll('[data-testid="provenance-badge"]');
    expect(badges.length).toBeGreaterThan(0);
  });

  it("signal with null quality passes null to CcProvenanceBadge (D5)", async () => {
    const w = mount(SignalsPanel, { global: { stubs: sharedStubs } });
    await flushPromises();
    const nullBadge = w.findAll('[data-testid="provenance-badge"]').find(
      (b) => b.attributes("data-quality") === "null"
    );
    expect(nullBadge).toBeDefined();
  });
});
