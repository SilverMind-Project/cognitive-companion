<template>
  <div>
    <v-select
      :model-value="modelValue"
      :items="cameraItems"
      item-title="name"
      item-value="id"
      :label="label"
      :hint="hint"
      :persistent-hint="!!hint"
      :loading="loading"
      multiple
      chips
      closable-chips
      density="comfortable"
      clearable
      placeholder="Select cameras"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <div v-if="suggestions.length > 0" class="mt-1">
      <span class="text-caption text-medium-emphasis">
        Suggested (best-effort coverage estimate):
      </span>
      <v-chip
        v-for="cam in suggestions"
        :key="cam.id"
        size="x-small"
        variant="tonal"
        class="ml-1 mt-1"
        :title="'Best-effort suggestion — confirm before saving'"
        @click="addSuggestion(cam.id)"
      >
        {{ cam.name }}
      </v-chip>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { cts } from "@/services/cts.js";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  label: { type: String, default: "Cameras" },
  hint: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue"]);

const allCameras = ref([]);
const loading = ref(false);

const cameraItems = computed(() =>
  allCameras.value.map((c) => ({ id: c.id, name: c.name || c.id })),
);

const suggestions = computed(() =>
  cameraItems.value.filter((c) => !(props.modelValue ?? []).includes(c.id)).slice(0, 3),
);

function addSuggestion(cameraId) {
  const current = [...(props.modelValue ?? [])];
  if (!current.includes(cameraId)) {
    emit("update:modelValue", [...current, cameraId]);
  }
}

async function fetchCameras() {
  loading.value = true;
  try {
    allCameras.value = await cts.getCameras();
  } catch {
    allCameras.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(fetchCameras);
</script>
