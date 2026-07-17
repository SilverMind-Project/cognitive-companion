import { ref } from "vue";
import { household } from "@/services/household";

/**
 * The saved floor-plan image/scale plus the SVG canvas dimensions derived
 * from it. canvasW/canvasH default to a placeholder aspect ratio and are
 * kept in sync with the floor plan's real pixel dimensions once loaded, so
 * spatial overlays (rooms, markers, heatmap bins) always project against
 * the same canvas the background image is drawn at.
 */
export function useFloorPlanCanvas() {
  const floorPlanUrl = ref(null);
  const fpWidth = ref(null);
  const fpHeight = ref(null);
  const fpMpp = ref(null);
  const canvasW = ref(1200);
  const canvasH = ref(800);

  async function loadFloorPlan() {
    try {
      const data = await household.getFloorPlan();
      floorPlanUrl.value = data.floor_plan_url;
      fpWidth.value = data.floor_plan_width;
      fpHeight.value = data.floor_plan_height;
      fpMpp.value = data.floor_meters_per_pixel;
      if (data.floor_plan_width && data.floor_plan_height) {
        canvasW.value = data.floor_plan_width;
        canvasH.value = data.floor_plan_height;
      }
    } catch {
      // Not configured yet — not an error.
    }
  }

  function applyUploadedFloorPlan(data) {
    floorPlanUrl.value = data.floor_plan_url;
    fpWidth.value = data.floor_plan_width;
    fpHeight.value = data.floor_plan_height;
    fpMpp.value = data.floor_meters_per_pixel;
    if (data.floor_plan_width && data.floor_plan_height) {
      canvasW.value = data.floor_plan_width;
      canvasH.value = data.floor_plan_height;
    }
  }

  return {
    floorPlanUrl,
    fpWidth,
    fpHeight,
    fpMpp,
    canvasW,
    canvasH,
    loadFloorPlan,
    applyUploadedFloorPlan,
  };
}
