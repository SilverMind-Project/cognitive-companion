import { describe, expect, it } from "vitest";
import {
  getKindPresentation,
  humanizeKind,
  SIGNAL_KIND_PRESENTATIONS,
} from "@/constants/signalKinds.js";

describe("signalKinds", () => {
  it("known kind returns its registered icon and blurb", () => {
    const presentation = getKindPresentation("tea_intent_suspected");
    expect(presentation.icon).toBe("mdi-kettle-steam-outline");
    expect(presentation.blurb).toBe("May be starting to make tea");
    expect(presentation.label).toBe("tea intent suspected");
  });

  it("same_clothes_suspected returns its registered icon and blurb", () => {
    const presentation = getKindPresentation("same_clothes_suspected");
    expect(presentation.icon).toBe("mdi-tshirt-crew-outline");
    expect(presentation.blurb).toBe("Appears to be wearing yesterday's clothes");
    expect(presentation.label).toBe("same clothes suspected");
  });

  it("unknown kind falls back to a generic humanized label and default icon", () => {
    // This is the forward-compatibility contract (DL-M06 Part E.5): a kind
    // this map has never heard of must still render, not throw or show
    // undefined. Required to exist before DL-M07/DL-M08 extend the map.
    const presentation = getKindPresentation("some_future_kind_nobody_registered");
    expect(presentation.label).toBe("some future kind nobody registered");
    expect(presentation.icon).toBe("mdi-bell-outline");
    expect(presentation.blurb).toBe("");
  });

  it("handles empty/undefined kind without throwing", () => {
    expect(() => getKindPresentation(undefined)).not.toThrow();
    expect(getKindPresentation(undefined).label).toBe("");
    expect(getKindPresentation("").label).toBe("");
  });

  it("humanizeKind replaces underscores with spaces", () => {
    expect(humanizeKind("bathroom_dwell_anomaly")).toBe("bathroom dwell anomaly");
  });

  it("SIGNAL_KIND_PRESENTATIONS has no duplicate-value entries silently overwritten", () => {
    // A sanity check that the registry object itself is well-formed, not a
    // functional requirement -- guards against a future copy/paste key typo.
    expect(Object.keys(SIGNAL_KIND_PRESENTATIONS).length).toBe(
      new Set(Object.keys(SIGNAL_KIND_PRESENTATIONS)).size,
    );
  });
});
