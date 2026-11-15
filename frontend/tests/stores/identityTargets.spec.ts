import { describe, it, expect, vi, beforeEach } from "vitest";

const api = vi.hoisted(() => ({ getIdentityTargets: vi.fn() }));
vi.mock("@/services/modules/identity_targets", () => api);

import { ApiError } from "@/services/http";
import { useIdentityTargetsStore } from "@/stores/identityTargets";

const ENVELOPE = {
  targets: [
    { identity_id: "resident", display_name: "Resident", is_active: true, is_guest: false },
  ],
  enrollment_available: true,
  gallery_available: false,
};

beforeEach(() => vi.clearAllMocks());

describe("identityTargets store", () => {
  it("loads once and shares a load already in flight", async () => {
    api.getIdentityTargets.mockResolvedValue(ENVELOPE);
    const store = useIdentityTargetsStore();

    await Promise.all([store.load(), store.load()]);
    await store.load();

    expect(api.getIdentityTargets).toHaveBeenCalledTimes(1);
    expect(store.nameOf("resident")).toBe("Resident");
    expect(store.nameOf("former-member")).toBe("former-member");
  });

  it("force reloads, for example after someone is named", async () => {
    api.getIdentityTargets.mockResolvedValue(ENVELOPE);
    const store = useIdentityTargetsStore();

    await store.load();
    await store.load(true);

    expect(api.getIdentityTargets).toHaveBeenCalledTimes(2);
  });

  it("keeps a 403 apart from other errors and never throws", async () => {
    api.getIdentityTargets.mockRejectedValueOnce(new ApiError(403, "forbidden"));
    const store = useIdentityTargetsStore();

    await store.load();
    expect([store.forbidden, store.error, store.loaded]).toEqual([true, "", false]);

    api.getIdentityTargets.mockRejectedValueOnce(new Error("network down"));
    await store.load();
    expect([store.forbidden, store.error]).toEqual([false, "network down"]);
  });
});
