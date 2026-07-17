<template>
  <div>
    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
      Select a room, then draw its polygon on the floor plan below. Right-click a vertex to delete
      it. Drag vertices to adjust. Click "Save polygon" to persist.
    </v-alert>

    <v-row class="floor-plan-layout">
      <v-col cols="12" md="9" class="floor-plan-main">
        <v-card class="glass-card floor-plan-visual-card floor-plan-editor-card">
          <v-card-title class="floor-plan-card-title d-flex align-center">
            <span>{{ editingRoom ? editingRoom.name : "Select a room" }}</span>
            <v-spacer />
            <v-btn
              v-if="editingRoom && editPolygon.length > 0"
              size="small"
              variant="text"
              color="error"
              class="mr-2"
              @click="editPolygon = []"
            >
              Clear
            </v-btn>
            <v-btn
              v-if="editingRoom"
              color="primary"
              variant="flat"
              size="small"
              :loading="savingRoom"
              :disabled="
                (editPolygon.length > 0 && editPolygon.length < 3) ||
                (editPolygon.length === 0 && !editingRoom?.floor_polygon)
              "
              @click="emit('save-polygon')"
            >
              {{
                editPolygon.length === 0 && editingRoom?.floor_polygon
                  ? "Delete polygon"
                  : "Save polygon"
              }}
            </v-btn>
          </v-card-title>
          <v-card-text class="pa-0">
            <PolygonOnSnapshot
              class="marauders-no-paint"
              :image-url="floorPlanUrl"
              image-class="cc-floor-plan-background-image marauders-no-paint"
              :model-value="editPolygon"
              :min-points="3"
              :readonly="!editingRoom"
              @update:model-value="editPolygon = $event"
            />
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="3" class="floor-plan-sidebar">
        <v-card class="glass-card floor-plan-sidebar-card">
          <v-card-title class="floor-plan-card-title">Rooms</v-card-title>
          <v-divider />
          <v-list density="compact" nav>
            <v-list-item
              v-for="room in rooms"
              :key="room.id"
              :title="room.name"
              :subtitle="room.floor_polygon ? `${room.floor_polygon.length} pts` : 'No polygon'"
              :active="editingRoom?.id === room.id"
              rounded="lg"
              @click="emit('select-room', room)"
            >
              <template #append>
                <v-icon v-if="room.floor_polygon" color="success" size="small"
                  >mdi-check-circle</v-icon
                >
              </template>
            </v-list-item>
            <v-list-item v-if="rooms.length === 0" class="text-medium-emphasis text-body-2">
              No rooms configured. Add rooms in the Rooms view.
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import PolygonOnSnapshot from "@/components/cts/PolygonOnSnapshot.vue";

defineProps({
  rooms: { type: Array, required: true },
  floorPlanUrl: { type: String, default: null },
  editingRoom: { type: Object, default: null },
  savingRoom: { type: Boolean, default: false },
});
const editPolygon = defineModel("editPolygon", { type: Array, required: true });
const emit = defineEmits(["select-room", "save-polygon"]);
</script>

<style scoped>
.floor-plan-editor-card :deep(.cc-spatial-editor) {
  min-height: 260px;
  max-height: min(560px, 58vh);
  border: 0;
  border-radius: 0;
}

.floor-plan-editor-card :deep(.cc-spatial-editor__image) {
  max-height: min(560px, 58vh);
}
</style>
