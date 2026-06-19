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
      <!-- Preset selector: casual caregivers pick a preset and never open the canvas (D26). -->
      <v-select
        :model-value="gate.vision?.preset_key ?? null"
        :items="presetItems"
        :loading="presetsLoading"
        label="Vision gate preset"
        density="compact"
        hide-details
        class="mb-2"
        placeholder="Choose a starting point"
        @update:model-value="onSelectPreset"
      />
      <div v-if="presetSummary" class="text-caption text-medium-emphasis mb-2">
        {{ presetSummary }}
      </div>

      <div class="d-flex align-center ga-2 mb-3">
        <v-btn
          variant="outlined"
          color="primary"
          size="small"
          prepend-icon="mdi-eye-outline"
          :disabled="!gate.vision?.gate_graph_rule_id"
          :loading="creatingGate"
          @click="showGateEditor = true"
        >
          Edit vision logic
        </v-btn>
        <span v-if="gate.vision?.gate_graph_rule_id" class="text-caption text-medium-emphasis">
          Gate graph #{{ gate.vision.gate_graph_rule_id }}
        </span>
      </div>

      <p class="text-caption text-medium-emphasis mb-3">
        Cameras for the vision check are the step's "Cameras" picker above; when
        left empty the system auto-selects from where she is (best-effort).
      </p>

      <!-- Sampling and cool-off (the three knobs, surfaced together so the
           caregiver's mental model matches the backend). Empty = inherit. -->
      <v-expansion-panels variant="accordion" class="mb-2">
        <v-expansion-panel>
          <v-expansion-panel-title class="text-body-2 font-weight-medium">
            Sampling and cool-off (advanced)
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.confirm?.window_s ?? null"
                  label="Lookback window (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.confirm.window_s)"
                  persistent-placeholder
                  @update:model-value="updateProfile('confirm', 'window_s', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.confirm?.max_frames ?? null"
                  label="Images (max frames)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.confirm.max_frames)"
                  persistent-placeholder
                  @update:model-value="updateProfile('confirm', 'max_frames', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.confirm?.min_confidence ?? null"
                  label="Min confidence (0-1)"
                  type="number"
                  step="0.05"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.confirm.min_confidence)"
                  persistent-placeholder
                  @update:model-value="updateProfile('confirm', 'min_confidence', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.confirm?.min_interval_s ?? null"
                  label="Cool-off (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.confirm.min_interval_s)"
                  persistent-placeholder
                  @update:model-value="updateProfile('confirm', 'min_interval_s', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.confirm?.max_disagreements ?? null"
                  label="Max disagreements"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.confirm.max_disagreements)"
                  persistent-placeholder
                  @update:model-value="updateProfile('confirm', 'max_disagreements', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-select
                  :model-value="gate.vision?.confirm?.on_max_disagreements ?? 'advance'"
                  :items="onMaxItems"
                  label="After max disagreements"
                  density="compact"
                  hide-details
                  @update:model-value="updateProfile('confirm', 'on_max_disagreements', $event)"
                />
              </v-col>
            </v-row>
            <p class="text-caption text-medium-emphasis mt-2 mb-0">
              Rate is set per poll node in the canvas; images = max frames;
              cool-off returns the last verdict within that window.
            </p>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Watch profile: off by default; observes quietly, never blocks. -->
        <v-expansion-panel>
          <v-expansion-panel-title class="text-body-2 font-weight-medium">
            Watch (background observing, advanced)
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-checkbox
              :model-value="gate.vision?.watch?.enabled ?? false"
              label="Enable background watch"
              density="compact"
              hide-details
              color="primary"
              class="mb-2"
              @update:model-value="updateProfile('watch', 'enabled', $event)"
            />
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.watch?.tick_s ?? null"
                  label="Tick interval (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.watch.tick_s)"
                  persistent-placeholder
                  @update:model-value="updateProfile('watch', 'tick_s', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.watch?.window_s ?? null"
                  label="Window (s)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.watch.window_s)"
                  persistent-placeholder
                  @update:model-value="updateProfile('watch', 'window_s', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.watch?.max_frames ?? null"
                  label="Images (max frames)"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.watch.max_frames)"
                  persistent-placeholder
                  @update:model-value="updateProfile('watch', 'max_frames', toNum($event))"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  :model-value="gate.vision?.watch?.auto_advance_k ?? null"
                  label="Auto-advance after K"
                  type="number"
                  density="compact"
                  hide-details
                  :placeholder="String(DEFAULTS.watch.auto_advance_k)"
                  persistent-placeholder
                  @update:model-value="updateProfile('watch', 'auto_advance_k', toNum($event))"
                />
              </v-col>
            </v-row>
            <v-checkbox
              :model-value="gate.vision?.watch?.auto_advance ?? false"
              label="Allow conservative auto-advance"
              density="compact"
              hide-details
              color="primary"
              class="mt-1"
              @update:model-value="updateProfile('watch', 'auto_advance', $event)"
            />
            <p class="text-caption text-medium-emphasis mt-2 mb-0">
              Watch quietly observes while she works; it never blocks her.
              Auto-advance is conservative and off by default.
            </p>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

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
import { ref, computed, onMounted } from "vue";
import ZonePicker from "./ZonePicker.vue";
import GateEditorDialog from "./GateEditorDialog.vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ kinds: ["response"] }),
  },
  roomId: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue"]);
const { notify } = useNotify();

// Resolved defaults mirrored from config/settings.yaml (VG0 section 3) so empty
// fields show the inherited value as a placeholder (precedence visible).
const DEFAULTS = {
  confirm: { window_s: 20, max_frames: 9, min_confidence: 0.7, min_interval_s: 15, max_disagreements: 2 },
  watch: { tick_s: 20, window_s: 4, max_frames: 3, auto_advance_k: 3 },
};

const showGateEditor = ref(false);
const presets = ref([]);
const presetsLoading = ref(false);
const creatingGate = ref(false);

const gate = computed(() => ({
  kinds: ["response"],
  mode: "any",
  ...props.modelValue,
}));

const modeOptions = [
  { title: "Any gate (advance when any passes)", value: "any" },
  { title: "All gates (advance when all pass)", value: "all" },
];

const onMaxItems = [
  { title: "Advance (defer to her word)", value: "advance" },
  { title: "Escalate", value: "escalate" },
];

const presetItems = computed(() =>
  presets.value.map((p) => ({ title: p.name, value: p.key })),
);

const presetSummary = computed(() => {
  const key = gate.value.vision?.preset_key;
  const preset = presets.value.find((p) => p.key === key);
  return preset?.summary ?? "";
});

onMounted(async () => {
  presetsLoading.value = true;
  try {
    presets.value = await api.getGatePresets();
  } catch {
    presets.value = [];
  } finally {
    presetsLoading.value = false;
  }
});

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

// Update a key inside vision.confirm / vision.watch, preserving the rest.
function updateProfile(profile, key, value) {
  const vision = gate.value.vision ?? {};
  const sub = { ...(vision[profile] ?? {}), [key]: value };
  emit("update:modelValue", { ...gate.value, vision: { ...vision, [profile]: sub } });
}

// Empty string -> null (inherit the default); otherwise a finite number.
function toNum(value) {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

async function onSelectPreset(key) {
  if (!key) return;
  // TODO(VG08): re-selecting a preset creates a new callable rule and orphans
  // the previous gate_graph_rule_id. Acceptable for v1; the gate-graph manager
  // (Part D, deferred) would offer reuse/cleanup of shared gate graphs.
  creatingGate.value = true;
  try {
    const rule = await api.createGateGraph({
      name: `Vision Gate ${Date.now()}`,
      from_preset: key,
    });
    const vision = { ...(gate.value.vision ?? {}), gate_graph_rule_id: rule.id, preset_key: key };
    emit("update:modelValue", { ...gate.value, vision });
  } catch (error) {
    notify.error(`Failed to create gate from preset: ${error.message || error}`);
  } finally {
    creatingGate.value = false;
  }
}

function onSaveGate(newGate) {
  emit("update:modelValue", newGate);
}
</script>
