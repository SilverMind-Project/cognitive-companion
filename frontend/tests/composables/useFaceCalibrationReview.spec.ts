import { describe, it, expect, vi, beforeEach } from "vitest";

const calibration = vi.hoisted(() => ({
  listCalibrationCandidates: vi.fn(),
  labelCalibrationCandidate: vi.fn(),
  rejectCalibrationCandidate: vi.fn(),
  deleteCalibrationCandidate: vi.fn(),
  getFaceCalibrationSummary: vi.fn(),
}));
const targetsApi = vi.hoisted(() => ({ getIdentityTargets: vi.fn() }));

vi.mock("@/services/modules/face_calibration", () => calibration);
vi.mock("@/services/modules/identity_targets", () => targetsApi);

import { useFaceCalibrationReview } from "@/composables/useFaceCalibrationReview";
import { ApiError } from "@/services/http";

const notify = { success: vi.fn(), error: vi.fn() };

function capture(id: string) {
  return {
    candidate_id: id,
    captured_at: "2026-10-21T09:00:00Z",
    camera_id: "cam-1",
    crop_url: null,
    quality_score: 0.4,
    quality_version: "heuristic-v1",
    yaw_deg: 0,
    pitch_deg: 0,
    nearest_similarity: 0.3,
    label_state: "unlabeled",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  calibration.getFaceCalibrationSummary.mockResolvedValue({ identities: [] });
  calibration.labelCalibrationCandidate.mockResolvedValue({});
  calibration.rejectCalibrationCandidate.mockResolvedValue({});
  // The shared list holds active members in name order (the server's contract).
  targetsApi.getIdentityTargets.mockResolvedValue({
    targets: [
      { identity_id: "amma", display_name: "Amma", is_active: true, is_guest: false },
      { identity_id: "grandma", display_name: "Grandma", is_active: true, is_guest: false },
      { identity_id: "nurse", display_name: "Nurse", is_active: true, is_guest: true },
    ],
    enrollment_available: true,
    gallery_available: true,
  });
});

describe("useFaceCalibrationReview", () => {
  it("keys non-guest residents from the shared list, in its name order", async () => {
    calibration.listCalibrationCandidates.mockResolvedValue({ candidates: [], next_cursor: null });
    const { keyedResidents, actions } = useFaceCalibrationReview(notify);
    await actions.load();
    expect(keyedResidents.value.map((r) => r.identity_id)).toEqual(["amma", "grandma"]);
  });

  it("labels the current capture as a resident and advances", async () => {
    calibration.listCalibrationCandidates.mockResolvedValue({
      candidates: [capture("c1"), capture("c2")],
      next_cursor: null,
    });
    const { current, actions } = useFaceCalibrationReview(notify);
    await actions.load();

    await actions.labelResident(1);

    expect(calibration.labelCalibrationCandidate).toHaveBeenCalledWith("c1", {
      label_kind: "member",
      label_identity_id: "grandma",
    });
    expect(current.value?.candidate_id).toBe("c2");
    expect(calibration.getFaceCalibrationSummary).toHaveBeenCalledTimes(2);
  });

  it("an unassigned number key does nothing", async () => {
    calibration.listCalibrationCandidates.mockResolvedValue({
      candidates: [capture("c1")],
      next_cursor: null,
    });
    const { actions } = useFaceCalibrationReview(notify);
    await actions.load();
    await actions.labelResident(5);
    expect(calibration.labelCalibrationCandidate).not.toHaveBeenCalled();
  });

  it("loads the next page when the queue empties", async () => {
    calibration.listCalibrationCandidates
      .mockResolvedValueOnce({ candidates: [capture("c1")], next_cursor: "page-2" })
      .mockResolvedValueOnce({ candidates: [capture("c9")], next_cursor: null });
    const { current, actions } = useFaceCalibrationReview(notify);
    await actions.load();

    await actions.labelNotEnrolled();

    expect(calibration.labelCalibrationCandidate).toHaveBeenCalledWith("c1", {
      label_kind: "not_enrolled",
    });
    expect(calibration.listCalibrationCandidates).toHaveBeenLastCalledWith("unlabeled", "page-2");
    expect(current.value?.candidate_id).toBe("c9");
  });

  it("keeps the capture and reports when a label fails", async () => {
    calibration.listCalibrationCandidates.mockResolvedValue({
      candidates: [capture("c1")],
      next_cursor: null,
    });
    calibration.labelCalibrationCandidate.mockRejectedValue(new Error("upstream down"));
    const { current, actions } = useFaceCalibrationReview(notify);
    await actions.load();

    await actions.labelNotAFace();

    expect(current.value?.candidate_id).toBe("c1");
    expect(notify.error).toHaveBeenCalledWith("Could not save the label: upstream down");
  });

  it("surfaces a load failure", async () => {
    calibration.listCalibrationCandidates.mockRejectedValue(new Error("502 Bad Gateway"));
    const { state, actions } = useFaceCalibrationReview(notify);
    await actions.load();
    expect(state.error).toBe("502 Bad Gateway");
    expect(state.forbidden).toBe(false);
  });

  it("reports a missing permission as forbidden, not as a retryable error", async () => {
    calibration.listCalibrationCandidates.mockRejectedValue(new ApiError(403, "Forbidden"));
    const { state, actions } = useFaceCalibrationReview(notify);
    await actions.load();
    expect(state.forbidden).toBe(true);
    expect(state.error).toBe("");
  });
});
