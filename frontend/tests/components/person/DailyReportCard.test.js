/**
 * DailyReportCard
 *
 * Verifies the card loads for itself: on first mount, and again when its person changes, always
 * with the current prop.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const getDailyReport = vi.fn();
vi.mock("@/services/api.js", () => ({
  api: {
    getDailyReport: (...args) => getDailyReport(...args),
    regenerateDailyReport: vi.fn(),
  },
}));

import DailyReportCard from "@/components/person/DailyReportCard.vue";

const slot = { template: "<div><slot /></div>" };
const stubs = {
  "v-alert": slot,
  "v-btn": slot,
  "v-card": slot,
  "v-card-text": slot,
  "v-card-title": slot,
  "v-chip": slot,
  "v-col": slot,
  "v-date-picker": slot,
  "v-icon": slot,
  "v-menu": slot,
  "v-progress-circular": slot,
  "v-progress-linear": slot,
  "v-row": slot,
  "v-skeleton-loader": slot,
  "v-spacer": slot,
};

const REPORT = {
  summary_text: "A steady day.",
  wellness_score: 86,
  sleep: {},
  meals: {},
  medication: {},
  bathroom_visits: {},
  exercise: {},
  tv: {},
  room_time: {},
  wellness_alerts: [],
};

const mountCard = (props = {}) =>
  mount(DailyReportCard, {
    props: { personId: "rose", date: "2026-11-04", ...props },
    global: { stubs },
  });

describe("DailyReportCard", () => {
  beforeEach(() => {
    getDailyReport.mockReset();
    getDailyReport.mockResolvedValue(REPORT);
  });

  it("loads the report on first mount", async () => {
    const w = mountCard();
    await flushPromises();
    expect(getDailyReport).toHaveBeenCalledWith("rose", "2026-11-04", {});
    expect(w.text()).toContain("A steady day.");
  });

  it("shows wellness on the backend's 0 to 100 scale", async () => {
    const w = mountCard();
    await flushPromises();
    expect(w.text()).toContain("Wellness 86 of 100");
  });

  it("requests the day the picker chose, as a calendar date", async () => {
    const w = mountCard();
    await flushPromises();
    await w.vm.onDateSelected(new Date(2026, 10, 2));
    await flushPromises();
    expect(getDailyReport).toHaveBeenLastCalledWith("rose", "2026-11-02", {});
  });

  it("reloads for the new person when the prop changes", async () => {
    const w = mountCard();
    await flushPromises();
    await w.setProps({ personId: "david" });
    await flushPromises();
    expect(getDailyReport).toHaveBeenLastCalledWith("david", "2026-11-04", {});
  });

  it("asks for room trends when they are switched on", async () => {
    const w = mountCard();
    await flushPromises();
    await w.setProps({ includeRoomTrends: true });
    await flushPromises();
    expect(getDailyReport).toHaveBeenLastCalledWith("rose", "2026-11-04", {
      include_room_trends: "true",
    });
  });
});
