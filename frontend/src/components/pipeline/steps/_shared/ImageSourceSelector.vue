<!--
  Shared image-source picker for steps that consume pipeline images
  (image_crop, llm_call, scene_analysis, person_identification).

  Encapsulates the "Image Source" select and its per-source sub-config:
  trigger frame count, reCamera selector (CameraSelector), time filter, a
  pipeline-output path, a unified media-window output path, and a CTS-window
  frames path. Steps toggle the optional blocks via props and add step-specific
  controls through the default slot, so the shared vocabulary lives in one
  place instead of being copy-pasted.

  All edits are emitted as a patched copy of the whole config object via
  update:modelValue, matching the existing per-step config convention.
-->
<template>
  <div>
    <v-select
      :model-value="modelValue.image_source"
      :items="sources"
      item-title="title"
      item-value="value"
      label="Image Source"
      class="mb-4"
      @update:model-value="patch({ image_source: $event })"
    />

    <v-text-field
      v-if="showMaxImages && modelValue.image_source !== 'none'"
      :model-value="modelValue.max_images"
      label="Max Images (total)"
      type="number"
      :min="1"
      :hint="maxImagesHint"
      persistent-hint
      class="mb-4"
      @update:model-value="patch({ max_images: Number($event) || 1 })"
    />

    <v-card v-if="showTriggerCard && isTrigger" variant="tonal" class="mb-4 pa-4">
      <div class="text-subtitle-2">Trigger Camera</div>
      <v-text-field
        :model-value="modelValue.trigger_images_count"
        label="Max frames"
        type="number"
        :min="0"
        hint="0 = include all available trigger frames"
        persistent-hint
        density="compact"
        class="mt-2"
        @update:model-value="patch({ trigger_images_count: Number($event) || 0 })"
      />
    </v-card>

    <CameraSelector
      v-if="isAdditional"
      :model-value="modelValue"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      @update:model-value="emit('update:modelValue', $event)"
    />

    <TimeFilterCard
      v-if="showTimeFilter && isAdditional"
      :model-value="modelValue.image_time_filter || {}"
      @update:model-value="patch({ image_time_filter: $event })"
    />

    <v-text-field
      v-if="modelValue.image_source === 'pipeline'"
      :model-value="modelValue.pipeline_image_path"
      label="Pipeline Image Path"
      hint="Dotted path to upstream step output, e.g. steps.crop_stove.outputs.images"
      persistent-hint
      class="mb-4"
      @update:model-value="patch({ pipeline_image_path: $event })"
    />

    <v-text-field
      v-if="modelValue.image_source === 'media_window'"
      :model-value="modelValue.pipeline_image_path"
      label="Media Window Output Path"
      hint="Dotted path to the unified output object, e.g. steps.media_window_poll_1.outputs"
      persistent-hint
      class="mb-4"
      @update:model-value="patch({ pipeline_image_path: $event })"
    />

    <!-- Step-specific extras (e.g. llm_call's sort/annotation options). -->
    <slot :is-additional="isAdditional" />
  </div>
</template>

<script>
import CameraSelector from "./CameraSelector.vue";
import TimeFilterCard from "./TimeFilterCard.vue";

// The standard image sources. llm_call prepends a "None (text only)" option.
export const DEFAULT_IMAGE_SOURCES = [
  { title: "Trigger frames", value: "trigger" },
  { title: "Selected reCameras", value: "additional" },
  { title: "Trigger plus selected reCameras", value: "both" },
  { title: "Pipeline step output", value: "pipeline" },
  { title: "Media window output", value: "media_window" },
];
</script>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Object, required: true },
  sources: { type: Array, default: () => DEFAULT_IMAGE_SOURCES },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  showMaxImages: { type: Boolean, default: false },
  showTriggerCard: { type: Boolean, default: false },
  showTimeFilter: { type: Boolean, default: false },
  maxImagesHint: { type: String, default: "Hard cap on total images" },
});

const emit = defineEmits(["update:modelValue"]);

const isTrigger = computed(
  () => props.modelValue.image_source === "trigger" || props.modelValue.image_source === "both",
);
const isAdditional = computed(
  () => props.modelValue.image_source === "additional" || props.modelValue.image_source === "both",
);

function patch(p) {
  emit("update:modelValue", { ...props.modelValue, ...p });
}
</script>
