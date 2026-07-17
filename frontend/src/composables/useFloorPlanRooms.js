import { ref } from "vue";
import { household } from "@/services/household";

/** The room list shared across live/edit/heatmap modes. */
export function useFloorPlanRooms(notify) {
  const rooms = ref([]);

  async function loadRooms() {
    try {
      rooms.value = await household.getRooms();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  function replaceRoom(updated) {
    const idx = rooms.value.findIndex((r) => r.id === updated.id);
    if (idx >= 0) rooms.value[idx] = updated;
  }

  return { rooms, loadRooms, replaceRoom };
}
