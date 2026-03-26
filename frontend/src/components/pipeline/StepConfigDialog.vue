<template>
  <v-dialog :model-value="modelValue" max-width="640" scrollable @update:model-value="$emit('update:modelValue', $event)">
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-cog</v-icon>
        Configure {{ humanize(localStep.step_type) }}
      </v-card-title>

      <v-card-text>
        <!-- Common: label -->
        <v-text-field
          v-model="localStep.label"
          label="Step Label"
          variant="outlined"
          density="comfortable"
          hint="Optional display name for this step"
          persistent-hint
          class="mb-4"
        />

        <!-- person_identification -->
        <template v-if="localStep.step_type === 'person_identification'">
          <v-text-field
            v-model="cfg.target_persons"
            label="Target Persons"
            variant="outlined"
            density="comfortable"
            hint="Comma-separated person names"
            persistent-hint
            class="mb-3"
          />
          <v-slider
            v-model="cfg.min_confidence"
            label="Min Confidence"
            :min="0"
            :max="1"
            :step="0.05"
            thumb-label="always"
            color="primary"
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.include_annotated_image"
            label="Include annotated image"
            density="comfortable"
            hide-details
          />
          <v-checkbox
            v-model="cfg.include_motion"
            label="Include motion data"
            density="comfortable"
            hide-details
          />
          <v-checkbox
            v-model="cfg.save_guest_images"
            label="Save guest images (unidentified faces)"
            density="comfortable"
            hide-details
          />
        </template>

        <!-- vision_analysis -->
        <template v-if="localStep.step_type === 'vision_analysis'">
          <v-textarea
            v-model="cfg.prompt"
            label="Vision Prompt"
            variant="outlined"
            rows="4"
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.use_annotated_image"
            label="Use annotated image"
            density="comfortable"
            hide-details
          />
        </template>

        <!-- logic_reasoning -->
        <template v-if="localStep.step_type === 'logic_reasoning'">
          <v-textarea
            v-model="cfg.prompt"
            label="Reasoning Prompt"
            variant="outlined"
            rows="4"
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.include_context"
            :items="contextKeys"
            label="Include Context Keys"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            class="mb-3"
          />
          <v-select
            v-model="cfg.response_format"
            :items="['default', 'activity_detection', 'custom']"
            label="Response Format"
            variant="outlined"
            density="comfortable"
            hint="JSON schema the LLM should return"
            persistent-hint
            class="mb-3"
          />
          <v-textarea
            v-if="cfg.response_format === 'custom'"
            v-model="cfg.response_schema"
            label="Custom Response Schema"
            variant="outlined"
            rows="3"
            hint="Instruction appended to the prompt describing the expected JSON keys"
            persistent-hint
          />
        </template>

        <!-- translation -->
        <template v-if="localStep.step_type === 'translation'">
          <v-text-field
            v-model="cfg.target_language"
            label="Target Language"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. es, fr, de, ja"
          />
        </template>

        <!-- notification -->
        <template v-if="localStep.step_type === 'notification'">
          <v-select
            v-model="cfg.alert_level"
            :items="['emergency', 'warning', 'info', 'reminder']"
            label="Alert Level"
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.channels"
            label="Notification Channels"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Type channel names and press Enter"
            persistent-hint
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.message_template"
            label="Message Template"
            variant="outlined"
            rows="3"
            hint="Use {{ variable }} for template substitution"
            persistent-hint
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.eink_targets"
            label="E-Ink Target Devices"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Sensor IDs of eink displays (empty = all eink devices)"
            persistent-hint
          />
        </template>

        <!-- ha_action -->
        <template v-if="localStep.step_type === 'ha_action'">
          <v-text-field
            v-model="cfg.domain"
            label="Domain"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. light, switch, script"
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.service"
            label="Service"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. turn_on, toggle"
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.entity_id"
            label="Entity ID"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. light.living_room"
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.data"
            label="Service Data (JSON)"
            variant="outlined"
            rows="3"
            placeholder='{ "brightness": 255 }'
          />
        </template>

        <!-- activity_detection -->
        <template v-if="localStep.step_type === 'activity_detection'">
          <v-text-field
            v-model="cfg.source_key"
            label="Source Key"
            variant="outlined"
            density="comfortable"
            hint="Pipeline data key containing LLM output (e.g. logic_response)"
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.activities_path"
            label="Activities Path"
            variant="outlined"
            density="comfortable"
            hint="Key within the source object containing the activity list"
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model.number="cfg.default_confidence"
            label="Default Confidence"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="0"
            :max="1"
            :step="0.05"
            hint="Fallback confidence when not provided per activity"
            persistent-hint
          />
        </template>

        <!-- wait -->
        <template v-if="localStep.step_type === 'wait'">
          <v-text-field
            v-model.number="cfg.minutes"
            label="Wait Duration (minutes)"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="0"
          />
        </template>

        <!-- condition -->
        <template v-if="localStep.step_type === 'condition'">
          <v-text-field
            v-model="cfg.expression"
            label="Condition Expression"
            variant="outlined"
            density="comfortable"
            hint="Expression evaluated at runtime to decide if pipeline continues"
            persistent-hint
          />
        </template>

        <!-- verification -->
        <template v-if="localStep.step_type === 'verification'">
          <div class="text-subtitle-2 mb-2">Activity Conditions</div>
          <div v-for="(cond, idx) in cfg.conditions" :key="idx" class="mb-4 pa-3 border rounded-lg">
            <div class="d-flex align-center mb-2">
              <span class="text-caption font-weight-bold">Condition {{ idx + 1 }}</span>
              <v-spacer />
              <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="cfg.conditions.splice(idx, 1)" />
            </div>
            <v-text-field
              v-model="cond.person_id"
              label="Person ID"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-text-field
              v-model="cond.activity_type"
              label="Activity Type"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-checkbox
              v-model="cond.completed"
              label="Expect completed (uncheck to verify NOT done)"
              density="compact"
              hide-details
              class="mb-2"
            />
            <v-select
              v-model="cond._time_mode"
              :items="['relative', 'fixed']"
              label="Time Window"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-text-field
              v-if="cond._time_mode !== 'fixed'"
              v-model.number="cond.within_minutes"
              label="Within Minutes"
              variant="outlined"
              density="compact"
              type="number"
              :min="0"
              class="mb-2"
            />
            <template v-if="cond._time_mode === 'fixed'">
              <v-text-field
                v-model="cond._window_start_time"
                label="Start Time (today)"
                variant="outlined"
                density="compact"
                type="time"
                hint="Start time for today's window"
                persistent-hint
                class="mb-2"
              />
              <v-text-field
                v-model="cond._window_end_time"
                label="End Time (today)"
                variant="outlined"
                density="compact"
                type="time"
                hint="End time for today's window"
                persistent-hint
                class="mb-2"
              />
            </template>
            <v-slider
              v-model="cond.min_confidence"
              label="Min Confidence"
              :min="0"
              :max="1"
              :step="0.05"
              thumb-label="always"
              color="primary"
            />
          </div>
          <v-btn variant="tonal" prepend-icon="mdi-plus" class="mb-4" @click="addCondition">
            Add Condition
          </v-btn>

          <v-select
            v-model="cfg.match_mode"
            :items="['all', 'any']"
            label="Match Mode"
            variant="outlined"
            density="comfortable"
            hint="'all' = every condition must pass, 'any' = at least one"
            persistent-hint
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.re_notify_if_failed"
            label="Re-notify if verification fails"
            density="comfortable"
            hide-details
            class="mb-3"
          />
          <v-text-field
            v-model.number="cfg.re_notify_delay_minutes"
            label="Re-notify Delay (minutes)"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="0"
          />
        </template>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" @click="save">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch, reactive } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  step: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue", "save"]);

const contextKeys = [
  "vision_result",
  "person_ids",
  "activity",
  "occupancy",
  "previous_alert",
  "sensor_data",
  "time_of_day",
  "room_context",
];

const localStep = reactive({
  step_type: "",
  label: "",
});

const cfg = reactive({});

const defaults = {
  person_identification: {
    target_persons: "",
    min_confidence: 0.6,
    include_annotated_image: true,
    include_motion: false,
    save_guest_images: false,
  },
  vision_analysis: {
    prompt: "",
    use_annotated_image: false,
  },
  logic_reasoning: {
    prompt: "",
    include_context: [],
    response_format: "default",
    response_schema: "",
  },
  translation: {
    target_language: "",
  },
  notification: {
    alert_level: "warning",
    channels: [],
    message_template: "",
    eink_targets: [],
  },
  ha_action: {
    domain: "",
    service: "",
    entity_id: "",
    data: "",
  },
  activity_detection: {
    source_key: "logic_response",
    activities_path: "activities",
    default_confidence: 0.8,
  },
  wait: {
    minutes: 5,
  },
  condition: {
    expression: "",
  },
  verification: {
    conditions: [],
    match_mode: "all",
    re_notify_if_failed: false,
    re_notify_delay_minutes: 5,
  },
};

watch(
  () => props.step,
  (step) => {
    if (!step) return;
    localStep.step_type = step.step_type || "";
    localStep.label = step.label || "";

    const base = defaults[step.step_type] || {};
    const incoming = step.config_json && typeof step.config_json === "object" ? step.config_json : {};

    // Reset cfg
    Object.keys(cfg).forEach((k) => delete cfg[k]);
    Object.assign(cfg, { ...base, ...incoming });

    // Add _time_mode and _window_*_time helpers to verification conditions for UI
    if (step.step_type === "verification" && Array.isArray(cfg.conditions)) {
      cfg.conditions = cfg.conditions.map((c) => ({
        ...c,
        _time_mode: c.window_start || c.window_end ? "fixed" : "relative",
        _window_start_time: c.window_start ? isoToTimeStr(c.window_start) : "",
        _window_end_time: c.window_end ? isoToTimeStr(c.window_end) : "",
      }));
    }

    // Normalize target_persons to comma string for person_identification
    if (step.step_type === "person_identification" && Array.isArray(cfg.target_persons)) {
      cfg.target_persons = cfg.target_persons.join(", ");
    }

    // Normalize ha_action data to string
    if (step.step_type === "ha_action" && typeof cfg.data === "object") {
      cfg.data = JSON.stringify(cfg.data, null, 2);
    }
  },
  { immediate: true }
);

/** Extract "HH:MM" from an ISO-8601 datetime string. */
function isoToTimeStr(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return "";
  }
}

/** Build an ISO-8601 UTC string for today at the given "HH:MM" local time. */
function timeStrToTodayISO(timeStr) {
  if (!timeStr) return null;
  const [h, m] = timeStr.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}

const STEP_LABELS = {
  activity_detection: "Record Activity",
  verification: "Verify Activity",
  person_identification: "Person Identification",
};

function humanize(type) {
  if (!type) return "Step";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function addCondition() {
  if (!cfg.conditions) cfg.conditions = [];
  cfg.conditions.push({
    person_id: "",
    activity_type: "",
    completed: true,
    _time_mode: "relative",
    within_minutes: 30,
    window_start: null,
    window_end: null,
    _window_start_time: "",
    _window_end_time: "",
    min_confidence: 0.5,
  });
}

function save() {
  const config = { ...cfg };

  // Normalize target_persons back to array
  if (localStep.step_type === "person_identification" && typeof config.target_persons === "string") {
    config.target_persons = config.target_persons
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  // Convert verification conditions: time inputs -> ISO timestamps, strip UI fields
  if (localStep.step_type === "verification" && Array.isArray(config.conditions)) {
    config.conditions = config.conditions.map(({ _time_mode, _window_start_time, _window_end_time, ...rest }) => {
      if (_time_mode === "fixed") {
        rest.window_start = timeStrToTodayISO(_window_start_time);
        rest.window_end = timeStrToTodayISO(_window_end_time);
        delete rest.within_minutes;
      } else {
        delete rest.window_start;
        delete rest.window_end;
      }
      return rest;
    });
  }

  // Parse ha_action data JSON string
  if (localStep.step_type === "ha_action" && typeof config.data === "string") {
    try {
      config.data = config.data.trim() ? JSON.parse(config.data) : {};
    } catch {
      config.data = {};
    }
  }

  emit("save", {
    step_type: localStep.step_type,
    label: localStep.label,
    config_json: config,
  });
  emit("update:modelValue", false);
}
</script>
