import { ref } from "vue";
import { cts } from "@/services/cts.js";

/**
 * The floor-region polygon draft (detected floor area, drawn/dragged over the camera image)
 * and its save/discard actions. `floorRegionDragIdx` is owned here (not privately in the
 * camera pane) so discardFloorRegion can cancel a drag in progress, exactly as the
 * pre-extraction script's single scope did.
 */
export function useFloorRegion(notify, selectedCameraId) {
  // floorRegionDraft: the polygon being reviewed/edited in normalised [0,1] image coords.
  // Each element is [x_norm, y_norm]. Null when no polygon is loaded.
  const floorRegionDraft = ref(null);
  // Whether the operator is actively dragging a floor-region vertex.
  const floorRegionDragIdx = ref(null);
  const floorRegionSaving = ref(false);

  async function saveFloorRegion(source) {
    if (!floorRegionDraft.value || !selectedCameraId.value) return;
    floorRegionSaving.value = true;
    try {
      await cts.postFloorRegion(selectedCameraId.value, floorRegionDraft.value, source);
      notify(
        source === "manual"
          ? "Floor region saved (manual)."
          : "Floor region accepted from auto-calibration.",
        "success",
      );
    } catch (e) {
      notify(`Floor region save failed: ${e.message}`, "error");
    } finally {
      floorRegionSaving.value = false;
    }
  }

  function discardFloorRegion() {
    floorRegionDraft.value = null;
    floorRegionDragIdx.value = null;
  }

  return {
    floorRegionDraft,
    floorRegionDragIdx,
    floorRegionSaving,
    saveFloorRegion,
    discardFloorRegion,
  };
}
