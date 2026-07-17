import { ref, computed } from "vue";
import { household } from "@/services/household.js";

/** Floor-plan image + scale for the calibration view (read-only here; edited elsewhere). */
export function useFloorPlan() {
  const floorPlanUrl = ref(null);
  const fpWidth = ref(null);
  const fpHeight = ref(null);
  const fpMpp = ref(null);

  const floorPlanReady = computed(() => !!floorPlanUrl.value);
  const scaleReady = computed(() => !!(fpMpp.value && fpWidth.value && fpHeight.value));

  async function loadFloorPlan() {
    try {
      const data = await household.getFloorPlan();
      floorPlanUrl.value = data.floor_plan_url;
      fpWidth.value = data.floor_plan_width;
      fpHeight.value = data.floor_plan_height;
      fpMpp.value = data.floor_meters_per_pixel;
    } catch {
      // Not configured yet.
    }
  }

  return {
    floorPlanUrl,
    fpWidth,
    fpHeight,
    fpMpp,
    floorPlanReady,
    scaleReady,
    loadFloorPlan,
  };
}
