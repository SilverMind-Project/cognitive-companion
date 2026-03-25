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
                  :items="['sensor_event', 'cron', 'manual']"
                  label="Trigger Type"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12">
                <v-textarea v-model="form.description" label="Description" variant="outlined" rows="2" />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field v-model="form.primary_sensor_id" label="Primary Sensor ID" variant="outlined" />
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
              <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="ctxDialog = true">
                Add Context
              </v-btn>
            </div>
            <v-list v-if="rule.contexts?.length">
              <v-list-item v-for="ctx in rule.contexts" :key="ctx.id">
                <template #prepend>
                  <v-chip size="small" color="info">{{ ctx.context_type }}</v-chip>
                </template>
                <v-list-item-title>{{ JSON.stringify(ctx.config_json) }}</v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteContext(ctx.id)" />
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-grey py-4">No context filters — rule applies everywhere</div>
          </v-card-text>
        </v-card>

        <v-dialog v-model="ctxDialog" max-width="500">
          <v-card rounded="xl">
            <v-card-title>Add Context Filter</v-card-title>
            <v-card-text>
              <v-select
                v-model="ctxForm.context_type"
                :items="['room', 'time_range', 'day_of_week', 'person_presence', 'person_activity']"
                label="Context Type"
                variant="outlined"
              />
              <v-textarea
                v-model="ctxConfigStr"
                label="Config (JSON)"
                variant="outlined"
                rows="4"
                placeholder='{"room_name": "Kitchen"}'
              />
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
                  Parent Rule #{{ dep.parent_rule_id }} — lookback {{ dep.lookback_minutes }}min
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
              <v-text-field v-model.number="depForm.parent_rule_id" label="Parent Rule ID" type="number" variant="outlined" />
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

// Settings form
const form = ref({});

// Contexts
const ctxDialog = ref(false);
const ctxForm = ref({ context_type: "room" });
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
    const config = JSON.parse(ctxConfigStr.value);
    await api.addRuleContext(ruleId.value, {
      context_type: ctxForm.value.context_type,
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

onMounted(loadRule);
</script>
