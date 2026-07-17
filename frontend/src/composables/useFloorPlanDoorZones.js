import { ref, watch } from "vue";
import { cts } from "@/services/cts";

/**
 * Door/transit zones. Owned by the orchestrator so `watch(mode)` sees the
 * live -> doors transition (see useFloorPlanCoverage for why this can't live
 * inside a v-if-gated panel).
 */
export function useFloorPlanDoorZones(mode, notify) {
  const doorZones = ref([]);
  const doorZonesLoading = ref(false);

  async function loadDoorZones() {
    doorZonesLoading.value = true;
    try {
      doorZones.value = await cts.getTransitZones();
    } catch (e) {
      notify.error(e.message || "Failed to load door zones");
    } finally {
      doorZonesLoading.value = false;
    }
  }

  watch(mode, (m) => {
    if (m === "doors") loadDoorZones();
  });

  return { doorZones, doorZonesLoading, loadDoorZones };
}
