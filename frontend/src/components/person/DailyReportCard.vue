<template>
  <div>
    <!-- Date selector and actions -->
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <v-menu v-model="dateMenu" :close-on-content-click="false" location="start">
        <template #activator="{ props: activatorProps }">
          <v-btn
            variant="tonal"
            prepend-icon="mdi-calendar"
            v-bind="activatorProps"
            :loading="loading"
          >
            {{ displayDate }}
          </v-btn>
        </template>
        <v-date-picker v-model="selectedDate" headers="" @update:model-value="onDateSelected" />
      </v-menu>

      <v-chip v-if="report" :color="wellnessColor" variant="tonal" class="ml-2">
        Wellness: {{ (report.wellness_score * 100).toFixed(0) }}%
      </v-chip>

      <v-spacer />

      <v-btn
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="regenerating"
        :disabled="!report"
        @click="regenerate"
      >
        Regenerate
      </v-btn>
    </div>

    <!-- LLM summary -->
    <v-alert v-if="report?.summary_text" type="info" variant="tonal" class="mb-4">
      {{ report.summary_text }}
    </v-alert>

    <!-- Wellness alerts -->
    <v-alert
      v-for="(alert, i) in report?.wellness_alerts || []"
      :key="i"
      :type="alertSeverityColor(alert.severity)"
      variant="tonal"
      class="mb-2"
    >
      <strong>{{ alert.title || alert.severity }}:</strong> {{ alert.message }}
    </v-alert>

    <!-- Report sections grid -->
    <v-row v-if="report" class="mt-2">
      <v-col v-for="section in reportSections" :key="section.key" cols="12" sm="6" md="4">
        <v-card variant="flat" class="report-section">
          <v-card-text class="pa-4">
            <div class="d-flex align-center mb-2">
              <v-icon :color="section.color" size="20" class="mr-2">{{ section.icon }}</v-icon>
              <span class="text-subtitle-2 font-weight-medium">{{ section.label }}</span>
            </div>
            <template v-for="(value, label) in section.data" :key="label">
              <div class="d-flex justify-space-between text-body-2">
                <span class="text-medium-emphasis">{{ label }}</span>
                <span class="font-weight-medium">{{ formatValue(value) }}</span>
              </div>
            </template>
            <div
              v-if="Object.keys(section.data).length === 0"
              class="text-caption text-medium-emphasis"
            >
              No data
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Room trends -->
    <v-card v-if="report?.room_trends" variant="flat" class="mb-4 mt-4">
      <v-card-text class="pa-4">
        <div class="d-flex align-center mb-2">
          <v-icon color="secondary" size="20" class="mr-2">mdi-home-circle</v-icon>
          <span class="text-subtitle-2 font-weight-medium">Room Trends</span>
        </div>
        <div
          v-for="(trend, room) in report.room_trends"
          :key="room"
          class="d-flex justify-space-between align-center text-body-2 py-1"
        >
          <span class="font-weight-medium">{{ room }}</span>
          <div class="d-flex ga-2 align-center">
            <v-chip
              size="x-small"
              :color="
                trend.overall_severity === 'warning' || trend.overall_severity === 'critical'
                  ? 'error'
                  : 'success'
              "
              variant="tonal"
            >
              {{ trend.overall_severity }}
            </v-chip>
            <v-chip
              v-if="trend.clutter_score > 0"
              size="x-small"
              variant="tonal"
              color="surface-variant"
            >
              Clutter: {{ trend.clutter_score.toFixed(1) }}
            </v-chip>
            <v-chip
              v-if="trend.trend_direction"
              size="x-small"
              variant="tonal"
              color="surface-variant"
            >
              {{ trend.trend_direction }}
            </v-chip>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <!-- Empty state -->
    <v-alert v-if="!loading && !report" type="info" variant="tonal" class="mt-4">
      No report available for {{ displayDate }}.
    </v-alert>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  personId: { type: String, required: true },
  date: { type: String, default: () => new Date().toISOString().slice(0, 10) },
  includeRoomTrends: { type: Boolean, default: false },
});

const loading = ref(false);
const regenerating = ref(false);
const dateMenu = ref(false);
const selectedDate = ref(props.date);
const report = ref(null);

const displayDate = computed(() => selectedDate.value || props.date);

const reportSections = computed(() => {
  if (!report.value) return [];
  const sections = [
    { key: "sleep", label: "Sleep", icon: "mdi-bed", color: "purple", data: report.value.sleep },
    {
      key: "meals",
      label: "Meals",
      icon: "mdi-silverware",
      color: "orange",
      data: report.value.meals,
    },
    {
      key: "medication",
      label: "Medication",
      icon: "mdi-pill",
      color: "red",
      data: report.value.medication,
    },
    {
      key: "bathroom_visits",
      label: "Bathroom",
      icon: "mdi-toilet",
      color: "blue",
      data: report.value.bathroom_visits,
    },
    {
      key: "exercise",
      label: "Exercise",
      icon: "mdi-run",
      color: "green",
      data: report.value.exercise,
    },
    {
      key: "tv",
      label: "Watching TV",
      icon: "mdi-television",
      color: "teal",
      data: report.value.tv,
    },
    {
      key: "room_time",
      label: "Room Time",
      icon: "mdi-floor-plan",
      color: "indigo",
      data: report.value.room_time,
    },
  ];
  return sections;
});

async function load() {
  loading.value = true;
  try {
    const params = {};
    if (props.includeRoomTrends) params.include_room_trends = "true";
    const data = await api.getDailyReport(props.personId, displayDate.value, params);
    report.value = data || null;
  } catch (e) {
    console.error("Failed to load daily report:", e);
    report.value = null;
  } finally {
    loading.value = false;
  }
}

async function regenerate() {
  regenerating.value = true;
  try {
    const params = {};
    if (props.includeRoomTrends) params.include_room_trends = "true";
    const data = await api.regenerateDailyReport(props.personId, displayDate.value, params);
    report.value = data || null;
  } catch (e) {
    console.error("Failed to regenerate report:", e);
  } finally {
    regenerating.value = false;
  }
}

function onDateSelected(date) {
  selectedDate.value = date;
  load();
}

function wellnessColor(score) {
  if (score == null) return "grey";
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "error";
}

function alertSeverityColor(severity) {
  if (!severity) return "info";
  const map = { ok: "success", info: "info", warning: "warning", critical: "error" };
  return map[severity] || "info";
}

function formatValue(value) {
  if (typeof value === "number") return value.toFixed(1);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value ?? "—";
}

defineExpose({ load });
</script>

<style scoped>
.report-section {
  height: 100%;
}

.report-section .d-flex:not(:first-child) {
  padding-top: 2px;
}
</style>
