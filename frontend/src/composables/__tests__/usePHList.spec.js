import { describe, it, expect, vi } from "vitest";
import { usePHList } from "../usePHList";

vi.mock("@/services/cts_ph", () => ({
  ctsPh: {
    list: vi.fn().mockResolvedValue({ items: [{ ph_id: "ph-1" }], total: 1 }),
    get: vi.fn(),
  },
}));

describe("usePHList", () => {
  it("returns { state, actions } shape", () => {
    const composable = usePHList();
    expect(composable).toHaveProperty("state");
    expect(composable).toHaveProperty("actions");
    expect(composable.state).toHaveProperty("items");
    expect(composable.state).toHaveProperty("loading");
    expect(composable.state).toHaveProperty("filters");
    expect(composable.actions).toHaveProperty("fetch");
    expect(composable.actions).toHaveProperty("handleWsEvent");
  });

  it("state.filters includes all ten filter params", () => {
    const { state } = usePHList();
    const filterKeys = Object.keys(state.filters);
    expect(filterKeys).toContain("identity_id");
    expect(filterKeys).toContain("room_id");
    expect(filterKeys).toContain("since");
    expect(filterKeys).toContain("until");
    expect(filterKeys).toContain("state");
    expect(filterKeys).toContain("include_transient");
    expect(filterKeys).toContain("min_duration_s");
    expect(filterKeys).toContain("search");
  });

  it("handleWsEvent updates row in place for cts_ph_update", async () => {
    const { state, actions } = usePHList();
    await actions.fetch();
    expect(state.items.value).toHaveLength(1);
    actions.handleWsEvent({
      type: "cts_ph_update",
      ph_id: "ph-1",
      current_identity_id: "alice",
      last_observed_at: "2026-01-01T00:00:00Z",
    });
    expect(state.items.value[0].current_identity_id).toBe("alice");
  });

  it("does not return flat refs at top level", () => {
    const composable = usePHList();
    expect(composable).not.toHaveProperty("items");
    expect(composable).not.toHaveProperty("loading");
    expect(composable).not.toHaveProperty("fetch");
  });
});
