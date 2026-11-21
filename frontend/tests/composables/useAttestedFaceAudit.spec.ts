import { describe, it, expect, vi, beforeEach } from "vitest";

const calibration = vi.hoisted(() => ({
  listAttestedFaces: vi.fn(),
  getAttestedFaceAuditSample: vi.fn(),
  getAttestedFaceAuditSummary: vi.fn(),
  auditAttestedFace: vi.fn(),
  promoteCalibrationCandidate: vi.fn(),
}));
vi.mock("@/services/modules/face_calibration", () => calibration);

import { useAttestedFaceAudit } from "@/composables/useAttestedFaceAudit";
import { ApiError } from "@/services/http";

const notify = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() });

function face(id: string, extra: Record<string, unknown> = {}) {
  return {
    candidate_id: id,
    captured_at: "2026-11-20T09:00:00Z",
    camera_id: "cam-1",
    crop_url: null,
    quality_score: 0.6,
    quality_version: "heuristic-v1",
    yaw_deg: 0,
    pitch_deg: 0,
    nearest_similarity: 0.3,
    label_state: "attested",
    label_kind: "member",
    label_identity_id: "amma",
    attestation_grade: "room",
    audit_verdict: null,
    promotion_eligible: true,
    promoted: false,
    pose_bin: "frontal",
    ...extra,
  };
}

const summary = (audited: number) => ({
  attested: 10,
  audited,
  correct: audited,
  wrong: 0,
  not_a_face: 0,
  precision_lower_bound: audited ? 0.5 : null,
  min_audited: 200,
  min_precision_lower_bound: 0.99,
  meets_bar: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  calibration.getAttestedFaceAuditSample.mockResolvedValue({
    candidates: [face("s1"), face("s2")],
  });
  calibration.getAttestedFaceAuditSummary.mockResolvedValue(summary(0));
  calibration.listAttestedFaces.mockResolvedValue({
    candidates: [face("g1"), face("g2", { audit_verdict: "wrong" }), face("g3")],
  });
});

describe("useAttestedFaceAudit", () => {
  it("loads the server's sample, the summary, and the grid without faces audited wrong", async () => {
    const { state, current, actions } = useAttestedFaceAudit(notify);
    await actions.load();
    expect(calibration.getAttestedFaceAuditSample).toHaveBeenCalledWith(25);
    expect(current.value?.candidate_id).toBe("s1");
    expect(state.exemplars.map((f) => f.candidate_id)).toEqual(["g1", "g3"]);
    expect(state.summary?.audited).toBe(0);
  });

  it("records a verdict, drops the face from the sample, and refreshes the summary", async () => {
    calibration.auditAttestedFace.mockResolvedValue(face("s1", { audit_verdict: "correct" }));
    const { state, current, actions } = useAttestedFaceAudit(notify);
    await actions.load();
    calibration.getAttestedFaceAuditSummary.mockResolvedValue(summary(1));
    await actions.audit("correct");
    expect(calibration.auditAttestedFace).toHaveBeenCalledWith("s1", "correct");
    expect(current.value?.candidate_id).toBe("s2");
    expect(state.summary?.audited).toBe(1);
  });

  it("keeps the face when the audit fails", async () => {
    calibration.auditAttestedFace.mockRejectedValue(new Error("upstream down"));
    const { state, actions } = useAttestedFaceAudit(notify);
    await actions.load();
    await actions.audit("wrong");
    expect(state.sample).toHaveLength(2);
    expect(notify.error).toHaveBeenCalledWith(expect.stringContaining("upstream down"));
  });

  it("promotes one face and marks it in the gallery", async () => {
    calibration.promoteCalibrationCandidate.mockResolvedValue({ pose_bin: "frontal" });
    const { state, actions } = useAttestedFaceAudit(notify);
    await actions.load();
    await actions.promote("g1");
    expect(calibration.promoteCalibrationCandidate).toHaveBeenCalledWith("g1");
    expect(state.exemplars[0]).toMatchObject({ promoted: true, promotion_eligible: false });
  });

  it("shows the forbidden state on 403 and an error with retry otherwise", async () => {
    calibration.getAttestedFaceAuditSample.mockRejectedValueOnce(
      new ApiError(403, { detail: "forbidden" }),
    );
    const { state, actions } = useAttestedFaceAudit(notify);
    await actions.load();
    expect(state.forbidden).toBe(true);
    calibration.getAttestedFaceAuditSample.mockRejectedValueOnce(new Error("boom"));
    await actions.load();
    expect(state.forbidden).toBe(false);
    expect(state.error).toContain("boom");
  });
});
