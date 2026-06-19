<template>
  <v-card variant="tonal" class="mb-3 pa-3">
    <div class="text-subtitle-2 mb-3">Completion Gate</div>

    <!-- Gate kinds -->
    <div class="d-flex flex-wrap ga-2 mb-3">
      <v-checkbox
        :model-value="true"
        label="Response (always required)"
        density="compact"
        hide-details
        disabled
        color="primary"
      />
      <v-checkbox
        :model-value="gate.kinds.includes('vision_confirm')"
        label="Vision confirm"
        density="compact"
        hide-details
        color="primary"
        @update:model-value="toggleKind('vision_confirm', $event)"
      />
      <v-checkbox
        :model-value="gate.kinds.includes('activity_signal')"
        label="Activity signal"
        density="compact"
        hide-details
        color="primary"
        @update:model-value="toggleKind('activity_signal', $event)"
      />
      <v-checkbox
        :model-value="gate.kinds.includes('zone_presence')"
        label="Zone presence"
        density="compact"
        hide-details
        color="primary"
        @update:model-value="toggleKind('zone_presence', $event)"
      />
    </div>

    <!-- Mode selector (only relevant when multiple gates selected) -->
    <v-select
      v-if="gate.kinds.length > 1"
      :model-value="gate.mode || 'any'"
      :items="modeOptions"
      label="Completion mode"
      density="compact"
      hide-details
      class="mb-3"
      style="max-width: 240px"
      @update:model-value="emit('update:modelValue', { ...gate, mode: $event })"
    />

    <!-- Vision confirm config -->
    <template v-if="gate.kinds.includes('vision_confirm')">
      <div class="d-flex align-center justify-space-between mb-2">
        <v-btn
          variant="outlined"
          color="primary"
          size="small"
          prepend-icon="mdi-eye-outline"
          class="my-1"
          @click="showGateEditor = true"
        >
          Edit vision logic
        </v-btn>
      </div>

      <v-textarea
        :model-value="gate.vision?.description ?? ''"
        label="What 'done' looks like (English)"
        rows="2"
        density="compact"
        hide-details
        placeholder="e.g. The kettle is full of water and placed on the hob."
        class="mb-2"
        @update:model-value="updateSub('vision', 'description', $event)"
      />
      <CameraPicker
        :model-value="gate.vision?.camera_ids ?? null"
        label="Camera override (vision check)"
        @update:model-value="updateSub('vision', 'camera_ids', $event)"
      />

      <GateEditorDialog
        v-model="showGateEditor"
        :gate="gate"
        @save="onSaveGate"
      />
    </template>

    <!-- Zone presence config -->
    <template v-if="gate.kinds.includes('zone_presence')">
      <ZonePicker
        :model-value="gate.zone?.zone_id ?? null"
        :room-id="roomId"
        label="Target zone"
        class="mb-2"
        @update:model-value="updateSub('zone', 'zone_id', $event)"
      />
    </template>

    <!-- Activity signal config -->
    <template v-if="gate.kinds.includes('activity_signal')">
      <v-row class="mt-0">
        <v-col cols="6">
          <v-text-field
            :model-value="gate.activity?.activity_type ?? ''"
            label="Activity type"
            density="compact"
            hide-details
            placeholder="e.g. pour_liquid"
            @update:model-value="updateSub('activity', 'activity_type', $event)"
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            :model-value="gate.activity?.window_s ?? ''"
            label="Window (seconds)"
            type="number"
            density="compact"
            hide-details
            @update:model-value="updateSub('activity', 'window_s', parseInt($event) || null)"
          />
        </v-col>
      </v-row>
    </template>
  </v-card>
</template>

<script setup>
import { ref, computed } from "vue";
import ZonePicker from "./ZonePicker.vue";
import CameraPicker from "./CameraPicker.vue";
import GateEditorDialog from "./GateEditorDialog.vue";

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ kinds: ["response"] }),
  },
  roomId: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue"]);

const showGateEditor = ref(false);

const gate = computed(() => ({
  kinds: ["response"],
  mode: "any",
  ...props.modelValue,
}));

const modeOptions = [
  { title: "Any gate (advance when any passes)", value: "any" },
  { title: "All gates (advance when all pass)", value: "all" },
];

function toggleKind(kind, enabled) {
  const current = [...(gate.value.kinds ?? ["response"])];
  const without = current.filter((k) => k !== kind);
  const next = enabled ? [...without, kind] : without;
  if (!next.includes("response")) next.unshift("response");
  emit("update:modelValue", { ...gate.value, kinds: next });
}

function updateSub(section, key, value) {
  const existing = gate.value[section] ?? {};
  emit("update:modelValue", { ...gate.value, [section]: { ...existing, [key]: value } });
}

function onSaveGate(newGate) {
  emit("update:modelValue", newGate);
}
</script>
