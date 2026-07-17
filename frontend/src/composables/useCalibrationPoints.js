import { ref } from "vue";
import { cts } from "@/services/cts.js";

/**
 * The point-correspondence list and the "solve" (postHomography) action.
 * `selectedCameraId` and `imgContentRect` are refs owned elsewhere (camera selection lives in
 * useCalibrationCamera; imgContentRect is set by the camera pane once its snapshot loads).
 * `pendingPixel`, `autoSuggestedPoints`, `existingCalibration`, and `result` are refs owned by
 * the view/sibling composables that clearPoints/runCalibration reset or set as a side effect,
 * exactly as the pre-extraction script did in one shared scope. `result` in particular is owned
 * by the view (not here) because useAutoCalibration also needs to null it on a fresh run, and
 * this composable needs autoSuggestedPoints from useAutoCalibration -- owning `result` here
 * would make the two composables depend on each other circularly.
 */
export function useCalibrationPoints(
  notify,
  selectedCameraId,
  imgContentRect,
  pendingPixel,
  autoSuggestedPoints,
  existingCalibration,
  result,
) {
  const points = ref([]);
  const calibrating = ref(false);

  function pointInQuadrant(q) {
    if (!imgContentRect.value) return false;
    const W = imgContentRect.value.naturalWidth;
    const H = imgContentRect.value.naturalHeight;
    return points.value.some(({ pixel: [px, py] }) => {
      const inRight = px >= W / 2;
      const inBottom = py >= H / 2;
      if (q === 0) return !inRight && !inBottom;
      if (q === 1) return inRight && !inBottom;
      if (q === 2) return !inRight && inBottom;
      if (q === 3) return inRight && inBottom;
      return false;
    });
  }

  function removePoint(i) {
    points.value.splice(i, 1);
    // If we removed a point while one is pending, keep the pending state.
  }

  function clearPoints() {
    points.value = [];
    pendingPixel.value = null;
    result.value = null;
    autoSuggestedPoints.value = [];
  }

  async function runCalibration() {
    if (points.value.length < 4) return;
    if (!imgContentRect.value) {
      notify("Load a camera snapshot first", "warning");
      return;
    }
    calibrating.value = true;
    result.value = null;
    try {
      result.value = await cts.postHomography(
        selectedCameraId.value,
        points.value,
        imgContentRect.value.naturalWidth,
        imgContentRect.value.naturalHeight,
      );
      existingCalibration.value = true;
      autoSuggestedPoints.value = [];
      notify("Calibration saved");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      calibrating.value = false;
    }
  }

  return {
    points,
    calibrating,
    pointInQuadrant,
    removePoint,
    clearPoints,
    runCalibration,
  };
}
