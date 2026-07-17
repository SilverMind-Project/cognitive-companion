import { ref, computed, watch } from "vue";
import { cts } from "@/services/cts";

/**
 * Camera-coverage polygons overlay. Owned by the orchestrator (not the
 * coverage panel) because `watch(mode)` lazy-loads on first entry into
 * coverage mode -- if this composable lived inside a v-if-gated panel
 * component, it would only be constructed once mode is already "coverage",
 * so the watcher would never see the live -> coverage transition that is
 * supposed to trigger the load.
 */
export function useFloorPlanCoverage(mode, notify) {
  const coverageLoading = ref(false);
  const coverageCameras = ref([]);
  const coverageImgReady = ref(false);
  const coverageImgW = ref(0);
  const coverageImgH = ref(0);

  function onCoverageImgLoad(el) {
    if (!el) return;
    coverageImgW.value = el.naturalWidth;
    coverageImgH.value = el.naturalHeight;
    coverageImgReady.value = true;
  }

  async function loadCoverage() {
    coverageLoading.value = true;
    try {
      const data = await cts.getVisibilityPolygons();
      coverageCameras.value = data.cameras || [];
    } catch (e) {
      notify(e.message, "error");
    } finally {
      coverageLoading.value = false;
    }
  }

  function toCoverageSvgPoints(polygon) {
    if (!coverageImgW.value || !coverageImgH.value) return "";
    return polygon
      .map(
        ([x, y]) => `${(x * coverageImgW.value).toFixed(1)},${(y * coverageImgH.value).toFixed(1)}`,
      )
      .join(" ");
  }

  function coverageCentroid(polygon) {
    if (!polygon || !polygon.length) return [0, 0];
    const sumX = polygon.reduce((s, [x]) => s + x, 0);
    const sumY = polygon.reduce((s, [, y]) => s + y, 0);
    return [
      (sumX / polygon.length) * coverageImgW.value,
      (sumY / polygon.length) * coverageImgH.value,
    ];
  }

  const uncalibratedCoverage = computed(() =>
    coverageCameras.value.filter((c) => !c.visibility_polygon),
  );

  watch(mode, (newMode) => {
    if (newMode === "coverage" && coverageCameras.value.length === 0) {
      loadCoverage();
    }
  });

  return {
    coverageLoading,
    coverageCameras,
    coverageImgReady,
    coverageImgW,
    coverageImgH,
    uncalibratedCoverage,
    onCoverageImgLoad,
    loadCoverage,
    toCoverageSvgPoints,
    coverageCentroid,
  };
}
