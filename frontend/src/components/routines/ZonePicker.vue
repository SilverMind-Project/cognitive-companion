<template>
  <v-select
    :model-value="modelValue"
    :items="zoneItems"
    item-title="name"
    item-value="id"
    :label="label"
    :loading="loading"
    :disabled="!roomId"
    density="comfortable"
    clearable
    :placeholder="roomId ? 'Select zone' : 'Select a room first'"
    :hint="roomId ? '' : 'A room must be known to list zones.'"
    persistent-hint
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>

<script setup>
import { ref, watch, onMounted } from "vue";
import { api } from "@/services/api.js";

const props = defineProps({
  modelValue: { type: Number, default: null },
  roomId: { type: Number, default: null },
  label: { type: String, default: "Zone" },
});

defineEmits(["update:modelValue"]);

const zoneItems = ref([]);
const loading = ref(false);

async function fetchZones() {
  if (!props.roomId) {
    zoneItems.value = [];
    return;
  }
  loading.value = true;
  try {
    const data = await api.listRoomZones(props.roomId);
    zoneItems.value = data.items ?? [];
  } catch {
    zoneItems.value = [];
  } finally {
    loading.value = false;
  }
}

watch(() => props.roomId, fetchZones);
onMounted(fetchZones);
</script>
