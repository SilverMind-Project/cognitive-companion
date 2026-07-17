import { ref } from "vue";
import { household } from "@/services/household";

/**
 * Edit-mode room polygon drawing. `rooms` and `replaceRoom` come from
 * useFloorPlanRooms so a saved polygon updates the same list the live and
 * heatmap modes read from.
 */
export function useRoomPolygonEditor(notify, replaceRoom) {
  const editingRoom = ref(null);
  const editPolygon = ref([]);
  const savingRoom = ref(false);

  function selectRoom(room) {
    editingRoom.value = room;
    editPolygon.value = room.floor_polygon ? JSON.parse(JSON.stringify(room.floor_polygon)) : [];
  }

  async function saveRoomPolygon() {
    if (!editingRoom.value) return;
    // Allow 0 points (delete polygon) or 3+ points (valid polygon), not 1-2.
    if (editPolygon.value.length > 0 && editPolygon.value.length < 3) return;
    savingRoom.value = true;
    const isDelete = editPolygon.value.length === 0;
    try {
      const updated = await household.putRoom(editingRoom.value.id, {
        ...editingRoom.value,
        floor_polygon: isDelete ? null : editPolygon.value,
      });
      replaceRoom(updated);
      editingRoom.value = updated;
      notify(isDelete ? "Room polygon removed" : "Room polygon saved");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      savingRoom.value = false;
    }
  }

  return { editingRoom, editPolygon, savingRoom, selectRoom, saveRoomPolygon };
}
