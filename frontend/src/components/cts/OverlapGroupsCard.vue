<template>
  <v-card class="glass-card mt-3">
    <v-card-title class="d-flex align-center text-body-1">
      Overlap Groups
      <v-spacer />
      <span class="text-caption text-medium-emphasis">{{ groups.length }}</span>
    </v-card-title>
    <v-card-subtitle class="text-caption text-wrap">
      Cameras that see the same floor area. Tracking merges one person seen by several uncalibrated
      cameras of a group by appearance; changes apply at the next tracking sync, within a minute.
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
          {{ (group.camera_ids || []).join(", ") }}
        </v-list-item-subtitle>
        <template #append>
          <v-btn
            icon="mdi-delete-outline"
            size="x-small"
            variant="text"
            color="error"
            :aria-label="`Delete overlap group ${group.name}`"
            :loading="deletingId === group.id"
            @click="removeGroup(group)"
          />
        </template>
      </v-list-item>
    </v-list>
    <div v-else class="pa-4 text-center text-body-2 text-medium-emphasis">
      No overlap groups. Without one, two uncalibrated cameras never merge a person.
    </div>
    <v-divider />
    <v-card-text>
      <v-text-field
        v-model="newName"
        label="Group name"
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
        Add group
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
    notify.success("Overlap group added");
    emit("changed");
  } catch (e) {
    notify.error(e.message || "Failed to add overlap group");
  } finally {
    creating.value = false;
  }
}

/** @param {OverlapGroup} group */
async function removeGroup(group) {
  const ok = await showConfirm(
    "Delete overlap group",
    `Delete "${group.name}" (${(group.camera_ids || []).join(", ")})? ` +
      "Tracking stops merging these cameras by appearance at the next sync.",
  );
  if (!ok) return;
  deletingId.value = group.id;
  try {
    await cts.deleteOverlapGroup(group.id);
    notify.success("Overlap group deleted");
    emit("changed");
  } catch (e) {
    notify.error(e.message || "Failed to delete overlap group");
  } finally {
    deletingId.value = null;
  }
}
</script>
