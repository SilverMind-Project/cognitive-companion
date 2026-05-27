import { describe, it, expect } from "vitest";
import { usePHDetail } from "../usePHDetail";

describe("usePHDetail", () => {
  it("returns { state, actions } shape", () => {
    const composable = usePHDetail();
    expect(composable).toHaveProperty("state");
    expect(composable).toHaveProperty("actions");
    expect(composable.state).toHaveProperty("detail");
    expect(composable.state).toHaveProperty("observations");
    expect(composable.state).toHaveProperty("loading");
    expect(composable.actions).toHaveProperty("fetch");
  });

  it("does not return flat refs at top level", () => {
    const composable = usePHDetail();
    expect(composable).not.toHaveProperty("detail");
    expect(composable).not.toHaveProperty("loading");
    expect(composable).not.toHaveProperty("fetch");
  });
});
