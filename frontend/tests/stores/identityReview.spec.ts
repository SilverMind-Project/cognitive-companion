import { describe, it, expect, vi } from "vitest";

const { getReviewVocabulary } = vi.hoisted(() => ({ getReviewVocabulary: vi.fn() }));
vi.mock("@/services/modules/identity_targets", () => ({ getReviewVocabulary }));

import { useIdentityReviewStore } from "@/stores/identityReview";
import { REVIEW_VOCABULARY } from "../support/reviewVocabulary";

describe("identityReview store", () => {
  it("loads once and fills the member into an effect", async () => {
    getReviewVocabulary.mockResolvedValue(REVIEW_VOCABULARY);
    const store = useIdentityReviewStore();

    await Promise.all([store.load(), store.load()]);
    await store.load();

    expect(getReviewVocabulary).toHaveBeenCalledTimes(1);
    expect(store.effect("reid_review", "is_member", "Amma")).toBe("Server: verified as Amma.");
    expect(store.effect("reid_review", "is_member")).toBe("Server: verified as the chosen member.");
    expect(store.guarantee("visitors")).toBe("Server: only naming changes enrollment.");
    expect(store.verdict("face_calibration", "new_person")).toBeNull();
  });

  it("records a failure, shows no effect text, and retries on the next load", async () => {
    getReviewVocabulary.mockReset();
    getReviewVocabulary.mockRejectedValueOnce(new Error("down"));
    getReviewVocabulary.mockResolvedValueOnce(REVIEW_VOCABULARY);
    const store = useIdentityReviewStore();

    await store.load();
    expect(store.error).toBe("down");
    expect(store.effect("visitors", "not_usable")).toBe("");

    await store.load();
    expect(store.error).toBe("");
    expect(store.effect("visitors", "not_usable")).toBe("Server: dismissed, nothing enrolled.");
  });
});
