import { ref } from "vue";
import { cts } from "@/services/cts.js";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket.js";

function normalizeSuggestedPoints(rawPoints) {
  return (rawPoints || [])
    .map((pt) => {
      const pixel = pt?.pixel;
      if (!Array.isArray(pixel) || pixel.length < 2) return null;
      const px = Number(pixel[0]);
      const py = Number(pixel[1]);
      if (!Number.isFinite(px) || !Number.isFinite(py)) return null;
      return { pixel: [Math.round(px), Math.round(py)], local_floor_m: pt.local_floor_m || null };
    })
    .filter(Boolean);
}

/**
 * Auto-calibration draft workflow: run the depth-based draft, show its suggested camera
 * points as "refine manually" ghosts, and track the live-stream minio_key so a re-run can
 * reuse the same frame the tracker just processed.
 *
 * Takes several refs owned by sibling composables/the view, exactly as the pre-extraction
 * script shared one closure over them: `selectedCameraId` (useCalibrationCamera),
 * `imgContentRect`/`inputMode`/`pendingPixel` (camera pane + view), `floorRegionDraft`
 * (useFloorRegion), `result` (useCalibrationPoints, cleared on a fresh auto-calibrate run).
 */
export function useAutoCalibration(
  notify,
  selectedCameraId,
  imgContentRect,
  inputMode,
  pendingPixel,
  floorRegionDraft,
  result,
) {
  const latestMinioKey = ref(null);
  const autoCalibrating = ref(false);
  const autoResult = ref(null);
  const autoSuggestedPoints = ref([]);

  function nearestAutoSuggestion(px, py) {
    if (!autoSuggestedPoints.value.length) return null;
    let best = null;
    let bestD2 = Infinity;
    for (const suggestion of autoSuggestedPoints.value) {
      const dx = suggestion.pixel[0] - px;
      const dy = suggestion.pixel[1] - py;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        best = suggestion;
        bestD2 = d2;
      }
    }
    return bestD2 <= 36 * 36 ? best : null;
  }

  function consumeAutoSuggestion(pixel) {
    autoSuggestedPoints.value = autoSuggestedPoints.value.filter((suggestion) => {
      const dx = suggestion.pixel[0] - pixel[0];
      const dy = suggestion.pixel[1] - pixel[1];
      return dx * dx + dy * dy > 36 * 36;
    });
  }

  async function runAutoCalibrate() {
    if (!selectedCameraId.value) return;
    autoCalibrating.value = true;
    autoResult.value = null;
    result.value = null;
    try {
      // Pass minio_key when available (from live stream); otherwise the BFF
      // fetches a fresh snapshot from the RTSP ingress automatically.
      const body = latestMinioKey.value ? { minio_key: latestMinioKey.value } : {};
      const res = await cts.autoCalibrate(selectedCameraId.value, body);
      autoResult.value = res;
      autoSuggestedPoints.value = [];
      if (res.floor_region_polygon) {
        floorRegionDraft.value = res.floor_region_polygon;
      }
      notify("Auto-calibration draft ready — review the suggested camera points below.", "success");
    } catch (e) {
      const msg = e?.response?.data?.detail?.message || e.message || "Auto-calibration failed.";
      notify(msg, "error");
    } finally {
      autoCalibrating.value = false;
    }
  }

  function populateFromAutoResult() {
    if (!autoResult.value || !imgContentRect.value) return;
    autoSuggestedPoints.value = normalizeSuggestedPoints(autoResult.value.suggested_points);
    inputMode.value = "pick";
    pendingPixel.value = null;
    autoResult.value = null;
    notify(
      `${autoSuggestedPoints.value.length} suggested camera points shown — click one, then anchor it on the floor plan.`,
      "info",
    );
  }

  function dismissAutoResult() {
    autoResult.value = null;
    autoSuggestedPoints.value = [];
  }

  // Track the latest MinIO key received via WebSocket for the selected camera. The
  // WebSocket is kept alive for the lifetime of this view; it is only used here to
  // harvest the latest minio_key for the auto-calibrate feature -- the live stream
  // itself is not rendered in the calibration view.
  function onLiveMessage(frame) {
    if (
      frame.type === "cts_live_frame" &&
      frame.camera_id === selectedCameraId.value &&
      frame.minio_key
    ) {
      latestMinioKey.value = frame.minio_key;
    }
  }
  useCtsWebSocket(onLiveMessage);

  return {
    latestMinioKey,
    autoCalibrating,
    autoResult,
    autoSuggestedPoints,
    nearestAutoSuggestion,
    consumeAutoSuggestion,
    runAutoCalibrate,
    populateFromAutoResult,
    dismissAutoResult,
  };
}
