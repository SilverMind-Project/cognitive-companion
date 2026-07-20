<!-- Backend: backend/steps/builtin/person_identification.py -->
<template>
  <!-- General tab: person identification settings -->
  <div v-if="tab === 'general'">
    <v-combobox
      :model-value="modelValue.target_persons"
      :items="availablePersons"
      label="Target Persons"
      multiple
      chips
      closable-chips
      hint="Select persons to identify, or leave empty for all"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, target_persons: $event })"
    />
    <v-slider
      :model-value="modelValue.min_confidence"
      label="Min Confidence"
      :min="0"
      :max="1"
      :step="0.05"
      thumb-label="always"
      color="primary"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, min_confidence: $event })"
    />
    <v-checkbox
      :model-value="modelValue.include_annotated_image"
      label="Include annotated image"
      class="mb-1"
      hide-details
      @update:model-value="
        emit('update:modelValue', { ...modelValue, include_annotated_image: $event })
      "
    />
    <v-checkbox
      :model-value="modelValue.include_motion"
      label="Include motion data"
      class="mb-1"
      hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, include_motion: $event })"
    />
    <v-checkbox
      :model-value="modelValue.save_guest_images"
      label="Save guest images (unidentified faces)"
      class="mb-4"
      hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, save_guest_images: $event })"
    />
  </div>

  <!-- Images tab -->
  <div v-else-if="tab === 'images'">
    <ImageSourceSelector
      :model-value="modelValue"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>

  <!-- Presence tab -->
  <div v-else-if="tab === 'presence'">
    <v-switch
      label="Record presence (update location state and history)"
      color="primary"
      hide-details
      class="mb-4"
    />

    <v-switch
      label="Record sightings (write PersonSighting rows)"
      color="primary"
      hide-details
      class="mb-4"
    />

    <v-select
      :model-value="modelValue.presence_room_source"
      :items="[
        { title: 'Trigger room', value: 'trigger' },
        { title: 'Source image room', value: 'source_image' },
        { title: 'Custom room', value: 'custom' },
      ]"
      item-title="title"
      item-value="value"
      label="Presence Room Source"
      class="mb-4"
      @update:model-value="
        emit('update:modelValue', { ...modelValue, presence_room_source: $event })
      "
    />

    <v-combobox
      v-if="modelValue.presence_room_source === 'custom'"
      :model-value="modelValue.presence_room_name"
      :items="availableRooms"
      label="Presence Room Name"
      hint="Custom room name for presence recording"
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, presence_room_name: $event })"
    />
  </div>
</template>

<script>
import ImageSourceSelector from "./_shared/ImageSourceSelector.vue";

export const stepDefaults = {
  target_persons: [],
  min_confidence: 0.6,
  include_annotated_image: true,
  include_motion: false,
  save_guest_images: false,
  additional_sensor_ids: [],
  image_source: "trigger",
  pipeline_image_path: "",

  presence_room_source: "trigger",
  presence_room_name: "",
};
export const stepTabs = [
  { key: "images", label: "Images", icon: "mdi-camera-outline" },
  { key: "presence", label: "Presence", icon: "mdi-map-marker-outline" },
];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.target_persons?.length) {
    out.push(chip(cfg.target_persons.join(", "), "mdi-account-outline", "indigo"));
  } else {
    out.push(chip("all persons", "mdi-account-group-outline", "indigo"));
  }
  if (cfg.min_confidence != null)
    out.push(chip(`>= ${Math.round(cfg.min_confidence * 100)}% conf`, "mdi-percent", "teal"));
  if (cfg.include_annotated_image)
    out.push(chip("annotated image", "mdi-image-edit-outline", undefined));
  if (cfg.write_movements_to_memory)
    out.push(chip("writes to memory", "mdi-database-arrow-up-outline", "purple"));
  return out;
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  availablePersons: { type: Array, default: () => [] },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
