<!-- Backend: backend/steps/builtin/verification.py -->
<template>
  <div v-if="tab === 'general'">
    <v-select
      :model-value="modelValue.match_mode"
      :items="['all', 'any']"
      label="Match Mode"
      hint="'all' = every condition must pass, 'any' = at least one"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, match_mode: $event })"
    />
    <v-checkbox
      :model-value="modelValue.re_notify_if_failed"
      label="Re-notify if verification fails"
      hide-details class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, re_notify_if_failed: $event })"
    />
    <v-text-field
      :model-value="modelValue.re_notify_delay_minutes"
      label="Re-notify Delay (minutes)"
      type="number"
      :min="0"
      @update:model-value="emit('update:modelValue', { ...modelValue, re_notify_delay_minutes: Number($event) || 0 })"
    />
  </div>

  <div v-else-if="tab === 'conditions'">
    <div class="d-flex align-center mb-3">
      <div class="text-subtitle-2">Activity Conditions</div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addCondition">Add Condition</v-btn>
    </div>
    <div v-if="!modelValue.conditions || !modelValue.conditions.length" class="text-center text-medium-emphasis py-4">
      No conditions yet.
    </div>
    <v-card v-for="(cond, idx) in (modelValue.conditions || [])" :key="idx" variant="outlined" class="mb-3 pa-4">
      <div class="d-flex align-center mb-3">
        <span class="text-caption font-weight-bold">Condition {{ idx + 1 }}</span>
        <v-spacer />
        <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="removeCondition(idx)" />
      </div>
      <v-row>
        <v-col cols="12" md="6">
          <v-combobox
            :model-value="cond.person_id"
            :items="availablePersons"
            label="Person ID (optional)"
            density="compact"
            clearable
            hint="Leave empty to match any person."
            persistent-hint
            @update:model-value="updateCondition(idx, 'person_id', $event)"
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-combobox
            :model-value="cond.activity_type"
            :items="activityTypes"
            label="Activity Type"
            density="compact"
            @update:model-value="updateCondition(idx, 'activity_type', $event)"
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-combobox
            :model-value="cond.room_name"
            :items="availableRooms"
            label="Room (optional)"
            density="compact"
            clearable
            @update:model-value="updateCondition(idx, 'room_name', $event)"
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-select
            :model-value="cond._time_mode"
            :items="['relative', 'fixed']"
            label="Time Window"
            density="compact"
            @update:model-value="updateCondition(idx, '_time_mode', $event)"
          />
        </v-col>
        <v-col v-if="cond._time_mode !== 'fixed'" cols="12">
          <v-text-field
            :model-value="cond.within_minutes"
            label="Within Minutes"
            density="compact"
            type="number"
            :min="0"
            @update:model-value="updateCondition(idx, 'within_minutes', Number($event) || 0)"
          />
        </v-col>
        <template v-if="cond._time_mode === 'fixed'">
          <v-col cols="6">
            <v-text-field
              :model-value="cond._window_start_time"
              label="Start Time (today)"
              density="compact" type="time"
              @update:model-value="updateCondition(idx, '_window_start_time', $event)"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              :model-value="cond._window_end_time"
              label="End Time (today)"
              density="compact" type="time"
              @update:model-value="updateCondition(idx, '_window_end_time', $event)"
            />
          </v-col>
        </template>
      </v-row>
      <v-checkbox
        :model-value="cond.completed"
        label="Expect completed (uncheck to verify NOT done)"
        density="compact" hide-details class="mt-2"
        @update:model-value="updateCondition(idx, 'completed', $event)"
      />
      <v-slider
        :model-value="cond.min_confidence"
        label="Min Confidence"
        :min="0" :max="1" :step="0.05"
        thumb-label="always"
        color="primary"
        class="mt-2"
        @update:model-value="updateCondition(idx, 'min_confidence', $event)"
      />
    </v-card>
  </div>
</template>

<script>
export const stepDefaults = {
  conditions: [],
  match_mode: "all",
  re_notify_if_failed: false,
  re_notify_delay_minutes: 5,
};
export const stepTabs = [
  { key: "conditions", label: "Conditions", icon: "mdi-check-decagram-outline" },
];

export function beforeSave(cfg, { localHHMMToUTCISO }) {
  const config = { ...cfg };
  if (Array.isArray(config.conditions)) {
    config.conditions = config.conditions.map(
      ({ _time_mode, _window_start_time, _window_end_time, ...rest }) => {
        if (_time_mode === "fixed") {
          rest.window_start = localHHMMToUTCISO(_window_start_time);
          rest.window_end = localHHMMToUTCISO(_window_end_time);
          delete rest.within_minutes;
        } else {
          delete rest.window_start;
          delete rest.window_end;
        }
        return rest;
      }
    );
  }
  return config;
}

export function onStepLoaded(cfg, { isoToLocalHHMM }) {
  if (Array.isArray(cfg.conditions)) {
    cfg.conditions = cfg.conditions.map((c) => ({
      room_name: "",
      ...c,
      _time_mode: c.window_start || c.window_end ? "fixed" : "relative",
      _window_start_time: c.window_start ? isoToLocalHHMM(c.window_start) : "",
      _window_end_time: c.window_end ? isoToLocalHHMM(c.window_end) : "",
    }));
  }
}
</script>

<script setup>
const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  availablePersons: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  activityTypes: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

function addCondition() {
  const conditions = [...(props.modelValue.conditions || [])];
  conditions.push({
    person_id: "",
    activity_type: "",
    room_name: "",
    completed: true,
    _time_mode: "relative",
    within_minutes: 30,
    window_start: null,
    window_end: null,
    _window_start_time: "",
    _window_end_time: "",
    min_confidence: 0.5,
  });
  emit("update:modelValue", { ...props.modelValue, conditions });
}

function removeCondition(idx) {
  const conditions = [...(props.modelValue.conditions || [])];
  conditions.splice(idx, 1);
  emit("update:modelValue", { ...props.modelValue, conditions });
}

function updateCondition(idx, key, value) {
  const conditions = (props.modelValue.conditions || []).map((c, i) =>
    i === idx ? { ...c, [key]: value } : c
  );
  emit("update:modelValue", { ...props.modelValue, conditions });
}
</script>
