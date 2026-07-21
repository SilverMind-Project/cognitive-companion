import { describe, expect, it } from "vitest";
import { ctxSummary } from "@/composables/useRuleContexts.js";

describe("ctxSummary", () => {
  describe("home_state", () => {
    it("summarizes an entity_id-based config", () => {
      const summary = ctxSummary({
        context_type: "home_state",
        config_json: { entity_id: "media_player.tv", states_any: ["playing", "on"] },
      });
      expect(summary).toBe("media_player.tv in playing/on");
    });

    it("summarizes a person/state config when entity_id is absent", () => {
      const summary = ctxSummary({
        context_type: "home_state",
        config_json: { person_id: "mom", state: "at_home" },
      });
      expect(summary).toBe("mom state = at_home");
    });

    it("falls back gracefully with no config at all", () => {
      const summary = ctxSummary({ context_type: "home_state", config_json: {} });
      expect(summary).toBe("any person state = ?");
    });
  });
});
