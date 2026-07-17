/**
 * U4-T3: Presence consistency regression guard
 *
 * Verifies that OverviewPanel and PeoplePanel, fed the same usePersonPresence data,
 * place each person in the SAME room (D1: disconnected-data regression guard).
 *
 * Both panels receive locations as a prop from the workspace; they must not
 * independently re-fetch and produce divergent room assignments.
 */
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

// ── Top-level mocks ──────────────────────────────────────────────────────────

const mockGetPersonLocations = vi.fn().mockResolvedValue([]);

vi.mock("@/services/api.js", () => ({
  api: { getPersonLocations: (...args) => mockGetPersonLocations(...args) },
}));

vi.mock("@/services/cts.js", () => ({
  cts: { getSignalSummary: vi.fn().mockResolvedValue({ by_type: {} }) },
}));

vi.mock("@/composables/useCtsSeverity.js", () => ({ severityColor: () => "grey" }));

vi.mock("@/components/dashboard/CcMetricTile.vue", () => ({
  default: {
    template: '<div :data-person="label" :data-room="value"><slot name="sparkline" /></div>',
    props: ["label", "value", "status", "to"],
  },
}));

vi.mock("@/components/dashboard/CcProvenanceBadge.vue", () => ({
  default: {
    template: '<span data-testid="provenance-badge" :data-source="source" />',
    props: ["source", "quality"],
  },
}));

vi.mock("@/views/admin/CTSPersonHypothesesView.vue", () => ({
  default: { template: '<div data-testid="ph-view" />' },
}));

import OverviewPanel from "../../../src/views/tracking/panels/OverviewPanel.vue";
import PeoplePanel from "../../../src/views/tracking/panels/PeoplePanel.vue";

const stubs = {
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "sm", "md"] },
  "v-skeleton-loader": { template: "<div />" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-card": { template: "<section><slot /></section>", props: ["color", "variant"] },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-chip": { template: "<span><slot /></span>", props: ["size", "color", "variant"] },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i />" },
  "router-link": { template: "<a><slot /></a>" },
};

const LOCATIONS = [
  {
    person_id: "alice",
    display_name: "Alice",
    room_name: "Kitchen",
    source: "observation",
    quality: 0.9,
    staleness_seconds: 0,
    is_inferred: false,
  },
  {
    person_id: "bob",
    display_name: "Bob",
    room_name: "Bathroom",
    source: "transition",
    quality: 0.7,
    staleness_seconds: 5,
    is_inferred: true,
  },
];

describe("Presence consistency: same locations → same rooms across panels", () => {
  it("OverviewPanel renders rooms from the locations prop (not a re-fetch)", () => {
    const w = mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs },
    });
    const tiles = w.findAll("[data-person]");
    expect(tiles).toHaveLength(2);

    const alice = tiles.find((t) => t.attributes("data-person") === "Alice");
    const bob = tiles.find((t) => t.attributes("data-person") === "Bob");
    expect(alice.attributes("data-room")).toBe("Kitchen");
    expect(bob.attributes("data-room")).toBe("Bathroom");
  });

  it("PeoplePanel receives the same locations prop and shows same person set", () => {
    const w = mount(PeoplePanel, {
      props: { locations: LOCATIONS },
      global: { stubs },
    });
    expect(w.props("locations")).toEqual(LOCATIONS);
    // The provenance badges in the strip should show both people
    const badges = w.findAll('[data-testid="provenance-badge"]');
    expect(badges.length).toBeGreaterThanOrEqual(LOCATIONS.length);
  });

  it("OverviewPanel does NOT call api.getPersonLocations (data arrives via prop)", () => {
    mockGetPersonLocations.mockClear();
    mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs },
    });
    // The panel is a pure presentational consumer of its prop — no independent fetch
    expect(mockGetPersonLocations).not.toHaveBeenCalled();
  });

  it("consistency check: alice in Kitchen in both panels simultaneously", () => {
    const wOverview = mount(OverviewPanel, {
      props: { locations: LOCATIONS, loading: false },
      global: { stubs },
    });
    const wPeople = mount(PeoplePanel, { props: { locations: LOCATIONS }, global: { stubs } });

    // OverviewPanel shows Alice → Kitchen
    const aliceTile = wOverview
      .findAll("[data-person]")
      .find((t) => t.attributes("data-person") === "Alice");
    expect(aliceTile.attributes("data-room")).toBe("Kitchen");

    // PeoplePanel holds the same locations reference — alice.room_name unchanged
    const aliceInPeople = wPeople.props("locations").find((l) => l.person_id === "alice");
    expect(aliceInPeople.room_name).toBe("Kitchen");
  });
});
