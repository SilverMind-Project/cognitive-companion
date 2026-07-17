import { ref, computed, watch } from "vue";
import { cts } from "@/services/cts.js";
import { qualityColor } from "@/composables/useAnnotationStyle.js";

// Project point through homography matrix.
function _projectPoint(H, px, py) {
  const hw = H[0][0] * px + H[0][1] * py + H[0][2];
  const hh = H[1][0] * px + H[1][1] * py + H[1][2];
  const hw3 = H[2][0] * px + H[2][1] * py + H[2][2];
  if (Math.abs(hw3) < 1e-9) return null;
  return [hw / hw3, hh / hw3];
}

/**
 * Live homography preview (debounced) as points are placed/moved, plus the derived coverage
 * polygon drawn on the floor-plan pane and the residual-based point coloring shared by both
 * panes. Reads `imgContentRect` (camera pane) and `fpImgRect`/`fpWidth`/`fpHeight`/`fpMpp`
 * (floor-plan pane + useFloorPlan) -- the one place this view's two panes' geometry meet.
 */
export function useCalibrationPreview(points, imgContentRect, fpImgRect, fpWidth, fpHeight, fpMpp, result) {
  const previewMatrix = ref(null);
  const previewResiduals = ref([]);
  const previewStatus = ref(null);
  let _previewDebounceTimer = null;

  function pointColor(i) {
    const residuals = result.value?.residuals_m ?? previewResiduals.value;
    if (!residuals || residuals.length <= i) return "var(--cc-brand)";
    return qualityColor(residuals[i]);
  }

  const previewCoveragePolygon = computed(() => {
    if (!previewMatrix.value) return null;
    if (!imgContentRect.value) return null;
    if (!fpImgRect.value) return null;
    if (!fpMpp.value || !fpWidth.value || !fpHeight.value) return null;

    const H = previewMatrix.value;
    const W = imgContentRect.value.naturalWidth;
    const Ht = imgContentRect.value.naturalHeight;
    const n = 20;

    const boundary = [];
    for (let i = 0; i < n; i++) {
      const t = i / n;
      boundary.push([W * t, 0]);
      boundary.push([W, Ht * t]);
      boundary.push([W * (1 - t), Ht]);
      boundary.push([0, Ht * (1 - t)]);
    }

    const floorPts = [];
    for (const [px, py] of boundary) {
      const fm = _projectPoint(H, px, py);
      if (fm === null) return null;
      floorPts.push(fm);
    }

    const totalW_m = fpWidth.value * fpMpp.value;
    const totalH_m = fpHeight.value * fpMpp.value;

    const svgPts = floorPts.map(([fx, fy]) => {
      const x = (fx / totalW_m) * fpImgRect.value.width;
      const y = (fy / totalH_m) * fpImgRect.value.height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    return svgPts.join(" ");
  });

  function schedulePreview() {
    if (points.value.length < 4) {
      previewMatrix.value = null;
      previewResiduals.value = [];
      previewStatus.value = null;
      return;
    }
    clearTimeout(_previewDebounceTimer);
    _previewDebounceTimer = setTimeout(async () => {
      try {
        const res = await cts.previewHomography(points.value);
        previewMatrix.value = res.matrix;
        previewResiduals.value = res.residuals_m;
        previewStatus.value = res.status;
      } catch {
        previewMatrix.value = null;
      }
    }, 400);
  }

  watch(points, schedulePreview, { deep: true });

  function disposePreviewTimer() {
    clearTimeout(_previewDebounceTimer);
  }

  return {
    previewStatus,
    previewCoveragePolygon,
    pointColor,
    disposePreviewTimer,
  };
}
