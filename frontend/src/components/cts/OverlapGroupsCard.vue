<template>
  <v-card class="glass-card">
    <v-card-title class="d-flex align-center text-body-1">
      Shared Views
      <v-spacer />
      <span class="text-caption text-medium-emphasis">{{ groups.length }}</span>
    </v-card-title>
    <v-card-subtitle class="text-caption text-wrap">
      Each group lists cameras that see the same floor area at the same time. Changes reach tracking
      within a minute.
    </v-card-subtitle>
    <v-divider class="mt-2" />
    <v-list v-if="groups.length > 0" density="compact">
      <v-list-item
        v-for="group in groups"
        :key="group.id"
        class="py-1"
        :data-testid="`overlap-group-${group.id}`"
      >
        <template #prepend>
          <v-icon color="success" size="small">mdi-vector-intersection</v-icon>
        </template>
        <v-list-item-title class="text-body-2">{{ group.name }}</v-list-item-title>
        <v-list-item-subtitle class="text-caption">
          {{ cameraLabels(group.camera_ids) }}
        </v-list-item-subtitle>
        <template #append>
          <v-btn
            icon="mdi-delete-outline"
            size="x-small"
            variant="text"
            color="error"
            :aria-label="`Delete shared view ${group.name}`"
            :loading="deletingId === group.id"
            @click="removeGroup(group)"
          />
        </template>
      </v-list-item>
    </v-list>
    <div v-else class="pa-4 text-center text-body-2 text-medium-emphasis">
      No shared views yet. Without one, a person seen at once by an uncalibrated camera and another
      camera becomes two tracks.
    </div>
    <v-divider />
    <v-card-text>
      <v-text-field
        v-model="newName"
        label="Name (for example, Living room)"
        density="comfortable"
        variant="outlined"
        hide-details="auto"
        class="mb-3"
        data-testid="overlap-group-name"
      />
      <v-select
        v-model="newCameraIds"
        :items="cameraItems"
        label="Cameras (two or more)"
        multiple
        chips
        closable-chips
        density="comfortable"
        variant="outlined"
        hide-details="auto"
        data-testid="overlap-group-cameras"
      />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-plus"
        :disabled="!canCreate"
        :loading="creating"
        data-testid="overlap-group-create"
        @click="createGroup"
      >
        Add shared view
      </v-btn>
    </v-card-actions>

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
import { computed, ref } from "vue";
import { cts } from "@/services/cts.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";

/**
 * @typedef {{ id: number, name: string, camera_ids: string[] }} OverlapGroup
 * @typedef {{ id: string, name?: string }} CameraOption
 */

const props = defineProps({
  /** @type {import('vue').PropType<OverlapGroup[]>} */
  groups: { type: Array, required: true },
  /** @type {import('vue').PropType<CameraOption[]>} */
  cameras: { type: Array, required: true },
});

const emit = defineEmits(["changed"]);

const { notify } = useNotify();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();

const newName = ref("");
const newCameraIds = ref([]);
const creating = ref(false);
const deletingId = ref(null);

const cameraItems = computed(() =>
  props.cameras.map((c) => ({ title: c.name ? `${c.name} (${c.id})` : c.id, value: c.id })),
);

const cameraNameById = computed(() =>
  Object.fromEntries(props.cameras.map((c) => [c.id, c.name || c.id])),
);

function cameraLabels(ids) {
  return (ids || []).map((id) => cameraNameById.value[id] || id).join(", ");
}

/**
 * Pre-fill the form from a suggestion; the operator names the group and may add cameras.
 * @param {string[]} cameraIds
 */
function prefill(cameraIds) {
  newCameraIds.value = [...cameraIds];
}

defineExpose({ prefill });

const canCreate = computed(() => newName.value.trim().length > 0 && newCameraIds.value.length >= 2);

async function createGroup() {
  if (!canCreate.value) return;
  creating.value = true;
  try {
    await cts.createOverlapGroup({
      name: newName.value.trim(),
      camera_ids: [...newCameraIds.value],
    });
    newName.value = "";
    newCameraIds.value = [];
    notify.success("Shared view added");
    emit("changed");
  } catch (e) {
    notify.error(e.message || "Failed to add shared view");
  } finally {
    creating.value = false;
  }
}

/** @param {OverlapGroup} group */
async function removeGroup(group) {
  const ok = await showConfirm(
    "Delete shared view",
    `Delete "${group.name}" (${cameraLabels(group.camera_ids)})? ` +
      "Tracking stops treating these cameras as one view within a minute.",
  );
  if (!ok) return;
  deletingId.value = group.id;
  try {
    await cts.deleteOverlapGroup(group.id);
    notify.success("Shared view deleted");
    emit("changed");
  } catch (e) {
    notify.error(e.message || "Failed to delete shared view");
  } finally {
    deletingId.value = null;
  }
}
</script>
