import { describe, it, expect, vi, beforeEach } from "vitest";

const api = vi.hoisted(() => ({ getIdentityReadiness: vi.fn() }));
vi.mock("@/services/modules/identity_readiness", () => api);

import { useIdentityReadiness } from "@/composables/useIdentityReadiness";
import { ApiError } from "@/services/http";

const ENVELOPE = {
  steps: [
    {
      key: "roster",
      state: "blocked",
      detail: "d",
      next_action: "enroll_members",
      optional: false,
    },
    {
      key: "capture",
      state: "unknown",
      detail: "d",
      next_action: "check_service",
      optional: false,
    },
  ],
  blocking_step: "roster",
  checked_at: "2026-11-14T09:00:00Z",
};

beforeEach(() => vi.clearAllMocks());

describe("useIdentityReadiness", () => {
  it("loads the envelope and indexes the steps by key", async () => {
    api.getIdentityReadiness.mockResolvedValue(ENVELOPE);
    const { state, stepByKey, actions } = useIdentityReadiness();

    await actions.load();

    expect(state.readiness).toEqual(ENVELOPE);
    expect(stepByKey.value.roster?.state).toBe("blocked");
    expect(stepByKey.value.capture?.next_action).toBe("check_service");
    expect(stepByKey.value.artifact).toBeUndefined();
    expect(state.loading).toBe(false);
  });

  it("reports a 403 as forbidden, not as an error", async () => {
    api.getIdentityReadiness.mockRejectedValue(new ApiError(403, "forbidden"));
    const { state, actions } = useIdentityReadiness();

    await actions.load();

    expect(state.forbidden).toBe(true);
    expect(state.error).toBe("");
  });

  it("keeps the error text for any other failure and clears it on retry", async () => {
    api.getIdentityReadiness.mockRejectedValueOnce(new Error("network down"));
    const { state, actions } = useIdentityReadiness();

    await actions.load();
    expect(state.error).toBe("network down");

    api.getIdentityReadiness.mockResolvedValueOnce(ENVELOPE);
    await actions.load();
    expect(state.error).toBe("");
    expect(state.readiness?.blocking_step).toBe("roster");
  });
});
