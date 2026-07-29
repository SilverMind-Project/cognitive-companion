<!-- Backend: backend/steps/builtin/semantic_memory_write.py -->
<template>
  <p class="text-body-2 text-medium-emphasis mb-4">
    This step reads what it writes from <code>pipeline_data</code>, so an upstream step (usually
    Scene Analysis) must populate the keys below. It does not author literal values.
  </p>

  <v-switch
    :model-value="modelValue.write_observation"
    label="Write observation"
    hint="Persist a scene observation built from the keys below."
    persistent-hint
    density="compact"
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, write_observation: $event })"
  />

  <template v-if="modelValue.write_observation">
    <v-text-field
      :model-value="modelValue.description_key"
      label="Description Key"
      density="compact"
      hint="pipeline_data path to the scene description (default: scene_description)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, description_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.detections_key"
      label="Detections Key"
      density="compact"
      hint="pipeline_data path to the detection list; supplies the object labels (default: scene_detections)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, detections_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.hazards_key"
      label="Hazards Key"
      density="compact"
      hint="pipeline_data path to the hazard alerts (default: scene_hazards)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, hazards_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.embedding_key"
      label="Embedding Key"
      density="compact"
      hint="pipeline_data path to the CLIP embedding (default: scene_embedding). Requires Scene Analysis with embeddings enabled."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, embedding_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.frames_key"
      label="Frames Key"
      density="compact"
      hint="pipeline_data key with the per-frame list (default: scene_images, from Scene Analysis). People are counted per frame and the maximum is stored; the flattened detection list would count one person once per frame."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, frames_key: $event })"
    />

    <v-text-field
      :model-value="modelValue.observed_at_key"
      label="Observed-at Key"
      density="compact"
      hint="pipeline_data key holding when the scene was captured (default: window_end, written by Media Window Poll). Blank records the write time instead."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, observed_at_key: $event })"
    />

    <v-select
      :model-value="modelValue.source"
      :items="['scene_intel', 'llm_vision', 'manual']"
      label="Source"
      density="compact"
      hint="Source tag recorded on the observation."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, source: $event })"
    />
  </template>

  <v-divider class="mb-4" />

  <v-switch
    :model-value="modelValue.write_movements"
    label="Write movements"
    hint="Persist person room-transitions linked to the observation above."
    persistent-hint
    density="compact"
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, write_movements: $event })"
  />

  <v-text-field
    v-if="modelValue.write_movements"
    :model-value="modelValue.movements_key"
    label="Movements Key"
    density="compact"
    hint="pipeline_data path to the room-transition list (default: room_transitions)"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, movements_key: $event })"
  />
</template>

<script>
// Keys mirror the backend config_schema exactly. They previously described a
// literal-value authoring model (write_type/description/object_list/...) that
// the backend never read, so nothing typed into this form reached the step.
export const stepDefaults = {
  source: "scene_intel",
  write_observation: true,
  write_movements: true,
  description_key: "scene_description",
  detections_key: "scene_detections",
  embedding_key: "scene_embedding",
  hazards_key: "scene_hazards",
  movements_key: "room_transitions",
  frames_key: "scene_images",
  observed_at_key: "window_end",
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.write_observation) out.push(chip("observation", "mdi-eye-outline", "blue-grey"));
  if (cfg.write_movements) out.push(chip("movements", "mdi-walk", "blue-grey"));
  if (cfg.source) out.push(chip(cfg.source, "mdi-tag-outline", undefined));
  return out;
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);
</script>
