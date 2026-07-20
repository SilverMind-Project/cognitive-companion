<!-- Backend: backend/steps/builtin/scene_analysis.py -->
<template>
  <!-- General tab -->
  <div v-if="tab === 'general'">
    <v-checkbox
      :model-value="modelValue.run_detect"
      label="Run YOLO object detection"
      hide-details
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_detect: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_describe"
      label="Run Florence-2 scene description"
      hide-details
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_describe: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_hazards"
      label="Evaluate hazard rules on detections"
      hide-details
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_hazards: $event })"
    />
    <v-checkbox
      :model-value="modelValue.run_embed"
      label="Run CLIP embedding (slow)"
      hide-details
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, run_embed: $event })"
    />
    <v-checkbox
      :model-value="modelValue.write_to_memory"
      label="Write result to semantic memory"
      hide-details
      class="mb-2"
      @update:model-value="emit('update:modelValue', { ...modelValue, write_to_memory: $event })"
    />
  </div>

  <!-- Images tab -->
  <div v-else-if="tab === 'images'">
    <ImageSourceSelector
      :model-value="modelValue"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      show-max-images
      show-trigger-card
      show-time-filter
      max-images-hint="Hard cap on total images analysed"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script>
import ImageSourceSelector from "./_shared/ImageSourceSelector.vue";

export const stepDefaults = {
  run_detect: true,
  run_describe: true,
  run_embed: false,
  run_hazards: true,
  write_to_memory: false,
  image_source: "trigger",
  max_images: 1,
  trigger_images_count: 0,
  additional_sensor_ids: [],
  additional_room_names: [],
  images_per_sensor: 1,
  sensor_frame_limits: {},
  image_time_filter: {},
  pipeline_image_path: "",
  pipeline_image_url_field: "url",
  pipeline_image_object_name_field: "object_name",
};
export const stepTabs = [{ key: "images", label: "Images", icon: "mdi-camera-outline" }];

export function chips(cfg, { chip }) {
  const out = [];
  const source = cfg.image_source || "trigger";
  out.push(chip(source, "mdi-image-outline", "teal"));
  const maxImgs = cfg.max_images ?? 1;
  if (maxImgs > 1) out.push(chip(`<= ${maxImgs} images`, "mdi-image-multiple-outline", "teal"));
  if (cfg.run_detect !== false) out.push(chip("detect", "mdi-eye-outline", "green"));
  if (cfg.run_describe !== false) out.push(chip("describe", "mdi-text-box-outline", "green"));
  if (cfg.run_hazards !== false) out.push(chip("hazards", "mdi-alert-outline", "orange"));
  if (cfg.run_embed) out.push(chip("embed", "mdi-vector-combine", "blue"));
  const addSensors = cfg.additional_sensor_ids?.length || 0;
  const addRooms = cfg.additional_room_names?.length || 0;
  if (addSensors > 0)
    out.push(
      chip(`+${addSensors} sensor${addSensors > 1 ? "s" : ""}`, "mdi-camera-plus-outline", "cyan"),
    );
  if (addRooms > 0)
    out.push(chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan"));
  if (cfg.output_key && cfg.output_key !== "scene_images")
    out.push(chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey"));
  return out;
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
