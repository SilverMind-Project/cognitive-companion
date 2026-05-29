/**
 * U4-T2: usePersonPresence
 *
 * Verifies:
 * - Calls api.getPersonLocations() — one fetch path (D1)
 * - Returns one entry per person; a person never appears twice
 * - Exposes loading/error state
 * - Preserves U2 envelope fields (quality, source, staleness_seconds)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";

// ── Mock api ──────────────────────────────────────────────────────────────────

const mockGetPersonLocations = vi.fn();

vi.mock("@/services/api.js", () => ({
  api: { getPersonLocations: (...args) => mockGetPersonLocations(...args) },
}));

import { usePersonPresence } from "../../src/composables/usePersonPresence.js";

const LOCATIONS = [
  {
    person_id: "alice", display_name: "Alice", room_id: 1, room_name: "Kitchen",
    source: "observation", quality: 0.9, staleness_seconds: 0, is_inferred: false,
  },
  {
    person_id: "bob", display_name: "Bob", room_id: 2, room_name: "Bathroom",
    source: "transition", quality: 0.7, staleness_seconds: 5, is_inferred: true,
  },
];

function mountComposable(pollMs = 99999) {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = usePersonPresence({ pollMs });
      return () => h("div");
    },
  });
  mount(Wrapper);
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetPersonLocations.mockResolvedValue(LOCATIONS);
});

describe("usePersonPresence", () => {
  it("calls api.getPersonLocations on mount (one fetch path)", async () => {
    mountComposable();
    await flushPromises();
    expect(mockGetPersonLocations).toHaveBeenCalledTimes(1);
  });

  it("returns one location per person", async () => {
    const { locations } = mountComposable();
    await flushPromises();
    expect(locations.value).toHaveLength(2);
    expect(locations.value.map((l) => l.person_id)).toContain("alice");
    expect(locations.value.map((l) => l.person_id)).toContain("bob");
  });

  it("deduplicates: a person never appears twice", async () => {
    mockGetPersonLocations.mockResolvedValue([
      ...LOCATIONS,
      { ...LOCATIONS[0], room_name: "Duplicate" },
    ]);
    const { locations } = mountComposable();
    await flushPromises();
    expect(locations.value.filter((l) => l.person_id === "alice")).toHaveLength(1);
  });

  it("sets loading=false after fetch resolves", async () => {
    const { loading } = mountComposable();
    await flushPromises();
    expect(loading.value).toBe(false);
  });

  it("sets error on fetch failure", async () => {
    mockGetPersonLocations.mockRejectedValue(new Error("Network error"));
    const { error } = mountComposable();
    await flushPromises();
    expect(error.value).toContain("Network error");
  });

  it("locations is empty array after failed fetch (never fabricates data)", async () => {
    mockGetPersonLocations.mockRejectedValue(new Error("timeout"));
    const { locations } = mountComposable();
    await flushPromises();
    expect(locations.value).toEqual([]);
  });

  it("preserves U2 envelope fields: quality, source, staleness_seconds", async () => {
    const { locations } = mountComposable();
    await flushPromises();
    const alice = locations.value.find((l) => l.person_id === "alice");
    expect(alice.quality).toBe(0.9);
    expect(alice.source).toBe("observation");
    expect(alice.staleness_seconds).toBe(0);
  });
});
