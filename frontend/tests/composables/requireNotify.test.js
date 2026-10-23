import { describe, expect, it, vi } from "vitest";

import { requireNotify, useNotify } from "@/composables/useNotify.js";
import { useRoutineBuilder } from "@/composables/useRoutineBuilder.js";

describe("requireNotify", () => {
  it("returns the notifier a view passes in", () => {
    const { notify } = useNotify();
    expect(requireNotify("useThing", notify)).toBe(notify);
  });

  it("rejects a missing or non-callable notifier at construction", () => {
    expect(() => requireNotify("useThing", undefined)).toThrow(
      "useThing requires a notify callback",
    );
    expect(() => requireNotify("useThing", { error: vi.fn() })).toThrow(TypeError);
  });

  it("makes a composable built without a notifier fail loudly", () => {
    expect(() => useRoutineBuilder()).toThrow("useRoutineBuilder requires a notify callback");
  });
});
