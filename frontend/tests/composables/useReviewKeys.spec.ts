import { describe, it, expect } from "vitest";

import { reviewKeyIntent } from "@/composables/useReviewKeys";

const ALL = ["is_member", "not_enrolled", "not_usable"] as const;

describe("reviewKeyIntent", () => {
  it("maps the shared keys", () => {
    expect(reviewKeyIntent("1", ALL)).toEqual({ kind: "member", position: 0 });
    expect(reviewKeyIntent("9", ALL)).toEqual({ kind: "member", position: 8 });
    expect(reviewKeyIntent("n", ALL)).toEqual({ kind: "verdict", verdict: "not_enrolled" });
    expect(reviewKeyIntent("x", ALL)).toEqual({ kind: "verdict", verdict: "not_usable" });
    expect(reviewKeyIntent("ArrowRight", ALL)).toEqual({ kind: "next" });
    expect(reviewKeyIntent("ArrowLeft", ALL)).toEqual({ kind: "previous" });
  });

  it("ignores keys for verdicts the surface does not accept", () => {
    expect(reviewKeyIntent("1", ["not_usable"])).toBeNull();
    expect(reviewKeyIntent("n", ["is_member", "not_usable"])).toBeNull();
    expect(reviewKeyIntent("0", ALL)).toBeNull();
    expect(reviewKeyIntent("q", ALL)).toBeNull();
  });
});
