<template>
  <v-card variant="outlined" class="pa-4">
    <div class="text-subtitle-2 mb-3">
      <v-icon size="small" class="mr-1">mdi-clock-outline</v-icon>
      Time Filter (optional)
    </div>
    <v-text-field
      :model-value="local.since_minutes"
      label="Since (minutes ago)"
      type="number"
      :min="0"
      class="mb-3"
      @update:model-value="updateField('since_minutes', $event)"
    />
    <v-row>
      <v-col cols="6">
        <v-text-field
          :model-value="local.time_start"
          label="Time Start"
          placeholder="08:00"
          @update:model-value="updateField('time_start', $event)"
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="local.time_end"
          label="Time End"
          placeholder="18:00"
          @update:model-value="updateField('time_end', $event)"
        />
      </v-col>
    </v-row>
  </v-card>
</template>

<script setup>
import { reactive, watch } from "vue";

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue"]);

const local = reactive({
  since_minutes: null,
  time_start: "",
  time_end: "",
});

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      local.since_minutes = val.since_minutes ?? null;
      local.time_start = val.time_start || "";
      local.time_end = val.time_end || "";
    }
  },
  { immediate: true },
);

function emitFilter() {
  const out = {};
  if (local.since_minutes != null && local.since_minutes !== "")
    out.since_minutes = Number(local.since_minutes);
  if (local.time_start) out.time_start = local.time_start;
  if (local.time_end) out.time_end = local.time_end;
  emit("update:modelValue", Object.keys(out).length > 0 ? out : {});
}

function updateField(key, val) {
  local[key] = val;
  emitFilter();
}
</script>
