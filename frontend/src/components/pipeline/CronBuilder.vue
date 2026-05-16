<template>
  <div>
    <div class="d-flex flex-wrap ga-2 mb-3">
      <v-btn
        v-for="opt in modeOptions"
        :key="opt.value"
        size="small"
        :variant="mode === opt.value ? 'flat' : 'outlined'"
        :color="mode === opt.value ? 'primary' : undefined"
        @click="mode = opt.value; onModeChange()"
      >{{ opt.label }}</v-btn>
    </div>

    <!-- Daily: time of day -->
    <v-row v-if="mode === 'daily'" dense>
      <v-col cols="6">
        <v-select v-model="hour" :items="hourItems" label="Hour" variant="outlined" density="compact" @update:model-value="onDailyTimeChange" />
      </v-col>
      <v-col cols="6">
        <v-select v-model="minute" :items="minuteItems" label="Minute" variant="outlined" density="compact" @update:model-value="onDailyTimeChange" />
      </v-col>
    </v-row>

    <!-- Weekly: days + time -->
    <template v-if="mode === 'weekly'">
      <v-row dense>
        <v-col v-for="d in dayOptions" :key="d.value" cols="auto">
          <v-checkbox v-model="selectedDays" :label="d.label" :value="d.value" density="compact" hide-details @update:model-value="onWeeklyChange" />
        </v-col>
      </v-row>
      <v-row dense class="mt-2">
        <v-col cols="6">
          <v-select v-model="hour" :items="hourItems" label="Hour" variant="outlined" density="compact" @update:model-value="onWeeklyChange" />
        </v-col>
        <v-col cols="6">
          <v-select v-model="minute" :items="minuteItems" label="Minute" variant="outlined" density="compact" @update:model-value="onWeeklyChange" />
        </v-col>
      </v-row>
    </template>

    <!-- Hourly: minute of hour -->
    <v-row v-if="mode === 'hourly'" dense>
      <v-col cols="12">
        <v-select v-model="minute" :items="minuteItems" label="Minute of hour" variant="outlined" density="compact" @update:model-value="onHourlyChange" />
      </v-col>
    </v-row>

    <!-- Interval: every N minutes -->
    <v-row v-if="mode === 'interval'" dense>
      <v-col cols="12">
        <v-text-field
          v-model.number="intervalMinutes"
          label="Minutes between runs"
          type="number"
          variant="outlined"
          density="compact"
          min="1"
          max="1440"
          hint="e.g. 15 = every 15 minutes"
          persistent-hint
          @update:model-value="onIntervalChange"
        />
      </v-col>
    </v-row>

    <!-- Custom: raw expression -->
    <v-row v-if="mode === 'custom'" dense>
      <v-col cols="12">
        <v-text-field
          v-model="rawExpression"
          label="Cron Expression"
          variant="outlined"
          density="compact"
          placeholder="*/5 * * * *"
          :error="!valid && rawExpression.length > 0"
          :error-messages="valid ? '' : validationError"
          @update:model-value="debouncedPreview"
        />
      </v-col>
    </v-row>

    <!-- Read-only expression display -->
    <v-row dense class="mt-1">
      <v-col cols="12">
        <v-text-field
          :model-value="expression"
          label="Expression"
          variant="outlined"
          density="compact"
          readonly
          hide-details
          class="cron-expression-readonly"
        />
      </v-col>
    </v-row>

    <!-- Human-readable + next runs -->
    <div v-if="valid && expression" class="text-caption mt-1">
      <div>{{ humanReadable }} ({{ timezone }})</div>
      <div v-if="nextRuns.length" class="mt-1">
        Next runs:
        <span v-for="(r, i) in nextRuns" :key="i" class="d-block text-xs">{{ formatDateTime(r) }}</span>
      </div>
    </div>
    <v-alert v-if="!valid && rawExpression.length > 0" type="error" density="compact" class="mt-2">
      {{ validationError }}
    </v-alert>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from "vue";
import { cronstrue } from "cronstrue";
import { api } from "../../services/api.js";
import { formatDateTime, getAppTimezone } from "../../services/timezone.js";

const props = defineProps({
  modelValue: { type: String, default: "" },
  timezone: { type: String, default: () => getAppTimezone() },
});

const emit = defineEmits(["update:modelValue"]);

const mode = ref("custom");
const modeOptions = [
  { value: "daily",    label: "Daily"      },
  { value: "weekly",   label: "Weekly"     },
  { value: "hourly",   label: "Hourly"     },
  { value: "interval", label: "Every N min"},
  { value: "custom",   label: "Custom"     },
];
const hour = ref(9);
const minute = ref(0);
const selectedDays = ref([1, 2, 3, 4, 5]); // Mon-Fri
const intervalMinutes = ref(15);
const rawExpression = ref("");
const humanReadable = ref("");
const nextRuns = ref([]);
const valid = ref(true);
const validationError = ref("");

const hourItems = Array.from({ length: 24 }, (_, i) => ({ title: `${i}:00`, value: i }));
const minuteItems = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => ({
  title: `:${String(m).padStart(2, "0")}`,
  value: m,
}));

const dayOptions = [
  { label: "Mon", value: 0 },
  { label: "Tue", value: 1 },
  { label: "Wed", value: 2 },
  { label: "Thu", value: 3 },
  { label: "Fri", value: 4 },
  { label: "Sat", value: 5 },
  { label: "Sun", value: 6 },
];

const expression = computed(() => rawExpression.value || buildExpression());

function buildExpression() {
  switch (mode.value) {
    case "daily":
      return `${minute.value} ${hour.value} * * *`;
    case "weekly": {
      const sortedDays = [...selectedDays.value].sort((a, b) => a - b);
      const dow = sortedDays.length ? sortedDays.join(",") : "*";
      return `${minute.value} ${hour.value} * * ${dow}`;
    }
    case "hourly":
      return `${minute.value} * * * *`;
    case "interval":
      return `*/${intervalMinutes.value} * * * *`;
    default:
      return rawExpression.value || "";
  }
}

function emitExpression(expr) {
  if (expr && expr !== rawExpression.value) {
    rawExpression.value = expr;
  }
  emit("update:modelValue", expr);
}

const onDailyTimeChange = () => emitExpression(buildExpression());
const onWeeklyChange = () => emitExpression(buildExpression());
const onHourlyChange = () => emitExpression(buildExpression());
const onIntervalChange = () => emitExpression(buildExpression());

function onModeChange() {
  if (mode.value !== "custom") {
    emitExpression(buildExpression());
  }
  if (rawExpression.value) {
    debouncedPreview();
  }
}

let previewTimer = null;
function debouncedPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(fetchPreview, 400);
}

async function fetchPreview() {
  const expr = expression.value;
  if (!expr || !expr.trim()) {
    valid.value = true;
    validationError.value = "";
    humanReadable.value = "";
    nextRuns.value = [];
    return;
  }
  try {
    humanReadable.value = cronstrue.toString(expr);
  } catch {
    humanReadable.value = "";
  }

  try {
    const result = await api.getCronPreview({ expression: expr, timezone: props.timezone });
    valid.value = result.valid;
    validationError.value = result.error || "";
    nextRuns.value = result.next_runs || [];

    // Use parsed result to suggest preset mode
    if (result.preset) {
      applyPresetFromParsed(result.parsed, result.preset);
    }
  } catch {
    valid.value = false;
    validationError.value = "Failed to validate expression";
  }
}

function applyPresetFromParsed(parsed, preset) {
  if (!parsed) return;
  mode.value = preset || "custom";

  // Extract minute
  const minField = parsed.minute;
  if (minField && minField.length === 1 && typeof minField[0] === "number") {
    minute.value = minField[0];
  }

  // Extract hour
  const hrField = parsed.hour;
  if (hrField && hrField.length === 1 && typeof hrField[0] === "number") {
    hour.value = hrField[0];
  }

  // Extract days of week
  const dowField = parsed.day_of_week;
  if (dowField) {
    const days = [];
    for (const d of dowField) {
      if (typeof d === "number") days.push(d);
    }
    if (days.length) selectedDays.value = days;
  }

  // Extract interval
  if (preset === "interval" && minField && minField.length === 1 && typeof minField[0] === "string") {
    const match = String(minField[0]).match(/^\*\/(\d+)$/);
    if (match) intervalMinutes.value = parseInt(match[1], 10);
  }
}

// Watch external modelValue changes
watch(
  () => props.modelValue,
  (newVal) => {
    if (newVal && newVal !== rawExpression.value) {
      rawExpression.value = newVal;
      debouncedPreview();
    }
  },
);

onMounted(() => {
  if (props.modelValue) {
    rawExpression.value = props.modelValue;
    fetchPreview();
  }
});
</script>

<style scoped>
.cron-expression-readonly :deep(input) {
  font-family: monospace;
  font-size: 0.9rem;
}
</style>
