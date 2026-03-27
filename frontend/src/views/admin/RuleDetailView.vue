<template>
  <div v-if="rule">
    <div class="d-flex align-center mb-4">
      <v-btn icon="mdi-arrow-left" variant="text" to="/admin/rules" />
      <h2 class="text-h5 ml-2">{{ rule.name }}</h2>
      <v-chip :color="rule.enabled ? 'success' : 'grey'" size="small" class="ml-3">
        {{ rule.enabled ? "Active" : "Disabled" }}
      </v-chip>
      <v-spacer />
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-play"
        :loading="executing"
        @click="executeRule"
      >
        Test Run
      </v-btn>
    </div>

    <v-tabs v-model="tab" color="primary">
      <v-tab value="settings">Settings</v-tab>
      <v-tab value="pipeline">Pipeline</v-tab>
      <v-tab value="contexts">Contexts</v-tab>
      <v-tab value="dependencies">Dependencies</v-tab>
      <v-tab value="executions">Executions</v-tab>
    </v-tabs>

    <v-window v-model="tab" class="mt-4">
      <!-- Settings Tab -->
      <v-window-item value="settings">
        <v-card rounded="xl">
          <v-card-text>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field v-model="form.name" label="Name" variant="outlined" />
              </v-col>
              <v-col cols="12" md="6">
                <v-select
                  v-model="form.trigger_type"
                  :items="triggerTypes"
                  label="Trigger Type"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12">
                <v-textarea v-model="form.description" label="Description" variant="outlined" rows="2" />
              </v-col>
              <v-col cols="12" md="6">
                <v-autocomplete
                  v-model="form.primary_sensor_id"
                  :items="sensorItems"
                  item-title="_label"
                  item-value="id"
                  label="Primary Sensor"
                  variant="outlined"
                  clearable
                  hint="The sensor that triggers this rule"
                  persistent-hint
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template #prepend>
                        <v-icon size="20" class="mr-2">{{ sensorIcon(item.raw.sensor_type) }}</v-icon>
                      </template>
                      <template #subtitle>
                        {{ item.raw.sensor_type }} · {{ item.raw.room_name || 'No room' }}
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="form.schedule_cron"
                  label="Cron Schedule"
                  variant="outlined"
                  placeholder="*/5 * * * *"
                  :disabled="form.trigger_type !== 'cron'"
                />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.cool_off_minutes" label="Cooloff (min)" type="number" variant="outlined" />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.max_daily_triggers" label="Max Daily" type="number" variant="outlined" />
              </v-col>
              <v-col cols="12" md="6">
                <v-switch v-model="form.enabled" label="Enabled" color="primary" />
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" @click="saveSettings">Save Settings</v-btn>
          </v-card-actions>
        </v-card>
      </v-window-item>

      <!-- Pipeline Tab -->
      <v-window-item value="pipeline">
        <v-card rounded="xl">
          <v-card-text>
            <PipelineBuilder :rule-id="ruleId" @updated="loadRule" />
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- Contexts Tab -->
      <v-window-item value="contexts">
        <v-card rounded="xl">
          <v-card-text>
            <div class="d-flex align-center mb-3">
              <h4 class="text-subtitle-1">Context Filters</h4>
              <v-spacer />
              <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCtxDialog">
                Add Context
              </v-btn>
            </div>
            <v-list v-if="rule.contexts?.length">
              <v-list-item v-for="ctx in rule.contexts" :key="ctx.id">
                <template #prepend>
                  <v-icon size="20" :color="ctxIcon(ctx.context_type).color" class="mr-3">
                    {{ ctxIcon(ctx.context_type).icon }}
                  </v-icon>
                </template>
                <v-list-item-title>
                  <v-chip size="small" color="info" variant="tonal" class="mr-2">{{ ctx.context_type }}</v-chip>
                  {{ ctxSummary(ctx) }}
                </v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteContext(ctx.id)" />
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-grey py-4">No context filters. This rule applies everywhere.</div>
          </v-card-text>
        </v-card>

        <!-- Context Filter Dialog -->
        <v-dialog v-model="ctxDialog" max-width="500">
          <v-card rounded="xl">
            <v-card-title>Add Context Filter</v-card-title>
            <v-card-text>
              <v-select
                v-model="ctxForm.context_type"
                :items="contextTypeItems"
                item-title="label"
                item-value="value"
                label="Context Type"
                variant="outlined"
                class="mb-3"
              />

              <!-- Room filter -->
              <template v-if="ctxForm.context_type === 'room'">
                <v-autocomplete
                  v-model="ctxForm.config.room_name"
                  :items="roomNames"
                  label="Room"
                  variant="outlined"
                  hint="Only trigger when the event is in this room"
                  persistent-hint
                />
              </template>

              <!-- Time range filter -->
              <template v-else-if="ctxForm.context_type === 'time_range'">
                <v-text-field
                  v-model="ctxForm.config.start_time"
                  label="Start Time"
                  variant="outlined"
                  type="time"
                  class="mb-3"
                />
                <v-text-field
                  v-model="ctxForm.config.end_time"
                  label="End Time"
                  variant="outlined"
                  type="time"
                />
              </template>

              <!-- Day of week filter -->
              <template v-else-if="ctxForm.context_type === 'day_of_week'">
                <v-select
                  v-model="ctxForm.config.days"
                  :items="dayItems"
                  label="Days"
                  variant="outlined"
                  multiple
                  chips
                  closable-chips
                  hint="Only trigger on selected days"
                  persistent-hint
                />
              </template>

              <!-- Person presence filter -->
              <template v-else-if="ctxForm.context_type === 'person_presence'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  clearable
                  class="mb-3"
                />
                <v-select
                  v-model="ctxForm.config.status"
                  :items="['home', 'away', 'unknown']"
                  label="Required Status"
                  variant="outlined"
                  hint="Only trigger when the person has this status"
                  persistent-hint
                  class="mb-3"
                />
                <v-autocomplete
                  v-if="ctxForm.config.status === 'home'"
                  v-model="ctxForm.config.room_name"
                  :items="roomNames"
                  label="In Room (optional)"
                  variant="outlined"
                  clearable
                  hint="Leave empty to match any room while home"
                  persistent-hint
                />
              </template>

              <!-- Person activity filter -->
              <template v-else-if="ctxForm.context_type === 'person_activity'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  clearable
                  class="mb-3"
                />
                <v-combobox
                  v-model="ctxForm.config.activity_type"
                  :items="activityTypeItems"
                  label="Activity Type"
                  variant="outlined"
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.within_minutes"
                  label="Within Minutes"
                  variant="outlined"
                  type="number"
                  hint="Check if activity occurred within this time window"
                  persistent-hint
                />
              </template>

              <!-- Fallback: raw JSON -->
              <template v-else>
                <v-textarea
                  v-model="ctxConfigStr"
                  label="Config (JSON)"
                  variant="outlined"
                  rows="4"
                  placeholder='{"key": "value"}'
                />
              </template>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="ctxDialog = false">Cancel</v-btn>
              <v-btn color="primary" @click="addContext">Add</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>

      <!-- Dependencies Tab -->
      <v-window-item value="dependencies">
        <v-card rounded="xl">
          <v-card-text>
            <div class="d-flex align-center mb-3">
              <h4 class="text-subtitle-1">Rule Dependencies</h4>
              <v-spacer />
              <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="depDialog = true">
                Add Dependency
              </v-btn>
            </div>
            <v-list v-if="rule.dependencies?.length">
              <v-list-item v-for="dep in rule.dependencies" :key="dep.id">
                <v-list-item-title>
                  {{ ruleNameById(dep.parent_rule_id) }} (Rule #{{ dep.parent_rule_id }}) &middot; lookback {{ dep.lookback_minutes }}min
                  <v-chip size="x-small" :color="dep.require_success ? 'success' : 'warning'" class="ml-2">
                    {{ dep.require_success ? "require success" : "require no success" }}
                  </v-chip>
                </v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteDep(dep.id)" />
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-grey py-4">No dependencies</div>
          </v-card-text>
        </v-card>

        <v-dialog v-model="depDialog" max-width="500">
          <v-card rounded="xl">
            <v-card-title>Add Dependency</v-card-title>
            <v-card-text>
              <v-autocomplete
                v-model="depForm.parent_rule_id"
                :items="otherRuleItems"
                item-title="_label"
                item-value="id"
                label="Parent Rule"
                variant="outlined"
                class="mb-3"
              />
              <v-text-field v-model.number="depForm.lookback_minutes" label="Lookback (min)" type="number" variant="outlined" />
              <v-switch v-model="depForm.require_success" label="Require Success" color="primary" />
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="depDialog = false">Cancel</v-btn>
              <v-btn color="primary" @click="addDep">Add</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>

      <!-- Executions Tab -->
      <v-window-item value="executions">
        <v-card rounded="xl">
          <v-data-table
            :headers="execHeaders"
            :items="executions"
            :loading="execLoading"
            item-value="id"
          >
            <template #item.status="{ item }">
              <v-chip
                :color="statusColor(item.status)"
                size="small"
              >
                {{ item.status }}
              </v-chip>
            </template>
            <template #item.started_at="{ item }">
              {{ formatDate(item.started_at) }}
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>
    </v-window>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
  <div v-else class="text-center py-8">
    <v-progress-circular indeterminate />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../services/api.js";
import PipelineBuilder from "../../components/pipeline/PipelineBuilder.vue";

const route = useRoute();
const ruleId = computed(() => Number(route.params.id));

const rule = ref(null);
const tab = ref("settings");
const executing = ref(false);
const snack = ref(false);
const snackText = ref("");
const snackColor = ref("success");

// Reference data from API
const allSensors = ref([]);
const allRooms = ref([]);
const allRules = ref([]);
const allPersons = ref([]);

const sensorItems = computed(() =>
  allSensors.value.map((s) => ({
    ...s,
    _label: `${s.name || s.id} (${s.sensor_type}${s.room_name ? ', ' + s.room_name : ''})`,
  }))
);

const roomNames = computed(() => allRooms.value.map((r) => r.name));
const personIds = computed(() => allPersons.value.map((p) => p.id));

const otherRuleItems = computed(() =>
  allRules.value
    .filter((r) => r.id !== ruleId.value)
    .map((r) => ({ ...r, _label: `${r.name} (#${r.id})` }))
);

const triggerTypes = [
  { title: "Sensor Event", value: "sensor_event" },
  { title: "Cron Schedule", value: "cron" },
  { title: "Manual", value: "manual" },
  { title: "Webhook", value: "webhook" },
];

const contextTypeItems = [
  { label: "Room", value: "room" },
  { label: "Time Range", value: "time_range" },
  { label: "Day of Week", value: "day_of_week" },
  { label: "Person Presence", value: "person_presence" },
  { label: "Person Activity", value: "person_activity" },
];

const dayItems = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const activityTypeItems = [
  "eating", "sleeping", "medication", "bathing", "walking",
  "watching_tv", "reading", "exercising", "cooking", "socializing",
];

// Settings form
const form = ref({});

// Contexts
const ctxDialog = ref(false);
const ctxForm = ref({ context_type: "room", config: {} });
const ctxConfigStr = ref("{}");

// Dependencies
const depDialog = ref(false);
const depForm = ref({ parent_rule_id: 0, lookback_minutes: 30, require_success: true });

// Executions
const executions = ref([]);
const execLoading = ref(false);
const execHeaders = [
  { title: "ID", key: "id" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at" },
];

function notify(text, color = "success") {
  snackText.value = text;
  snackColor.value = color;
  snack.value = true;
}

function sensorIcon(type) {
  const map = {
    camera: "mdi-cctv",
    presence: "mdi-motion-sensor",
    button: "mdi-gesture-tap-button",
    light: "mdi-lightbulb",
    eink: "mdi-image-edit",
  };
  return map[type] || "mdi-access-point";
}

function ctxIcon(type) {
  const map = {
    room: { icon: "mdi-floor-plan", color: "primary" },
    time_range: { icon: "mdi-clock-outline", color: "orange" },
    day_of_week: { icon: "mdi-calendar-week", color: "purple" },
    person_presence: { icon: "mdi-account-check", color: "success" },
    person_activity: { icon: "mdi-run", color: "info" },
  };
  return map[type] || { icon: "mdi-filter", color: "grey" };
}

function ctxSummary(ctx) {
  const c = ctx.config_json || {};
  switch (ctx.context_type) {
    case "room": return c.room_name || "Any room";
    case "time_range": return `${c.start_time || '?'} - ${c.end_time || '?'}`;
    case "day_of_week": return Array.isArray(c.days) ? c.days.join(", ") : JSON.stringify(c);
    case "person_presence": return `${c.person_id || 'any person'} is ${c.status || '?'}${c.room_name ? ' in ' + c.room_name : ''}`;
    case "person_activity": return `${c.person_id || 'any person'}: ${c.activity_type || '?'}`;
    default: return JSON.stringify(c);
  }
}

function ruleNameById(id) {
  const r = allRules.value.find((r) => r.id === id);
  return r ? r.name : "";
}

function openCtxDialog() {
  ctxForm.value = { context_type: "room", config: {} };
  ctxConfigStr.value = "{}";
  ctxDialog.value = true;
}

async function loadRule() {
  try {
    rule.value = await api.getRule(ruleId.value);
    form.value = {
      name: rule.value.name,
      description: rule.value.description || "",
      enabled: rule.value.enabled,
      trigger_type: rule.value.trigger_type,
      schedule_cron: rule.value.schedule_cron || "",
      primary_sensor_id: rule.value.primary_sensor_id || "",
      cool_off_minutes: rule.value.cool_off_minutes,
      max_daily_triggers: rule.value.max_daily_triggers,
    };
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadReferenceData() {
  const [sensors, rooms, rules, persons] = await Promise.all([
    api.getSensors().catch(() => []),
    api.getRooms().catch(() => []),
    api.getRules().catch(() => []),
    api.getPersons().catch(() => []),
  ]);
  allSensors.value = Array.isArray(sensors) ? sensors : [];
  allRooms.value = Array.isArray(rooms) ? rooms : [];
  allRules.value = Array.isArray(rules) ? rules : [];
  allPersons.value = Array.isArray(persons) ? persons : [];
}

async function saveSettings() {
  try {
    await api.updateRule(ruleId.value, form.value);
    await loadRule();
    notify("Settings saved");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function executeRule() {
  executing.value = true;
  try {
    const result = await api.executeRule(ruleId.value);
    notify(`Execution started (#${result.execution_id})`);
    await loadExecutions();
  } catch (e) {
    notify(e.message, "error");
  }
  executing.value = false;
}

async function addContext() {
  try {
    let config;
    const t = ctxForm.value.context_type;
    if (["room", "time_range", "day_of_week", "person_presence", "person_activity"].includes(t)) {
      config = { ...ctxForm.value.config };
    } else {
      config = JSON.parse(ctxConfigStr.value);
    }
    await api.addRuleContext(ruleId.value, {
      context_type: t,
      config_json: config,
    });
    ctxDialog.value = false;
    await loadRule();
    notify("Context added");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteContext(ctxId) {
  try {
    await api.deleteRuleContext(ruleId.value, ctxId);
    await loadRule();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addDep() {
  try {
    await api.addRuleDep(ruleId.value, depForm.value);
    depDialog.value = false;
    await loadRule();
    notify("Dependency added");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteDep(depId) {
  try {
    await api.deleteRuleDep(ruleId.value, depId);
    await loadRule();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadExecutions() {
  execLoading.value = true;
  try {
    executions.value = await api.getWorkflows({ rule_id: ruleId.value, limit: 50 });
  } catch (e) {
    console.error("Failed to load executions:", e);
    executions.value = [];
  }
  execLoading.value = false;
}

function statusColor(status) {
  const map = { completed: "success", failed: "error", running: "info", waiting: "warning", cancelled: "grey" };
  return map[status] || "grey";
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

watch(tab, (val) => {
  if (val === "executions") loadExecutions();
});

onMounted(() => {
  loadRule();
  loadReferenceData();
});
</script>
