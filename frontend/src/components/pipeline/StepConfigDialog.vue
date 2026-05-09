<template>
  <v-dialog
    :model-value="modelValue"
    width="1440"
    max-width="98vw"
    :fullscreen="$vuetify.display.smAndDown"
    scrollable
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card class="cc-glass step-config-card d-flex flex-column">
      <!-- Header -->
      <div class="step-config-header px-6 py-4 d-flex align-center">
        <v-avatar size="40" class="step-config-icon mr-3">
          <v-icon color="white">{{ stepIcon }}</v-icon>
        </v-avatar>
        <div class="flex-grow-1">
          <div class="text-overline text-medium-emphasis">Configure Step</div>
          <div class="text-h6 font-weight-bold tracking-tight">{{ humanize(localStep.step_type) }}</div>
        </div>
        <v-btn icon="mdi-close" variant="text" @click="$emit('update:modelValue', false)" />
      </div>

      <v-divider />

      <!-- Body: tabs left, content + variable reference right -->
      <div class="step-config-body d-flex flex-grow-1 overflow-hidden">
        <!-- Left vertical tabs -->
        <v-tabs
          v-model="activeTab"
          direction="vertical"
          color="primary"
          class="step-config-tabs flex-shrink-0"
        >
          <v-tab
            v-for="t in tabs"
            :key="t.key"
            :value="t.key"
            class="justify-start"
            :prepend-icon="t.icon"
          >
            {{ t.label }}
          </v-tab>
        </v-tabs>

        <v-divider vertical />

        <!-- Tab content + variable reference -->
        <div class="d-flex flex-grow-1 overflow-hidden">
          <div class="step-config-content flex-grow-1 px-6 py-5">
            <v-window v-model="activeTab">
              <v-window-item
                v-for="tabItem in tabs"
                :key="tabItem.key"
                :value="tabItem.key"
              >
                <!-- General tab: step label + step-type config -->
                <template v-if="tabItem.key === 'general'">
                  <v-text-field
                    v-model="localStep.label"
                    label="Step Label"
                    hint="Used as the key in pipeline_data.steps — must be unique, lowercase, letters/digits/underscores only"
                    persistent-hint
                    :rules="labelRules"
                    :error-messages="labelUniqueError"
                    class="mb-5"
                  />
                </template>

                <KeepAlive>
                  <component
                    :is="stepComponent"
                    :key="`${localStep.step_type}_${tabItem.key}`"
                    v-model="cfg"
                    :tab="tabItem.key"
                    :all-steps="allSteps"
                    :available-persons="availablePersons"
                    :available-rooms="availableRooms"
                    :available-channels="availableChannels"
                    :camera-sensor-items="cameraSensorItems"
                    :ha-entity-items="haEntityItems"
                    :ha-media-player-items="haMediaPlayerItems"
                    :eink-sensor-items="einkSensorItems"
                    :image-template-items="imageTemplateItems"
                    :llm-model-items="llmModelItems"
                    :activity-types="activityTypes"
                    :context-keys="contextKeys"
                    :known-signal-kinds="knownSignalKinds"
                    :severity-items="severityItems"
                  />
                </KeepAlive>
              </v-window-item>
            </v-window>
          </div>

          <!-- Pipeline Variables sidebar -->
          <v-divider vertical />
          <div class="step-config-vars px-4 py-5 d-none d-md-flex flex-column" style="position: relative;">
            <div class="d-flex align-center mb-3">
              <v-icon size="small" class="mr-2" color="primary">mdi-code-braces</v-icon>
              <div class="text-subtitle-2 font-weight-bold">Pipeline Variables</div>
            </div>
            <div class="text-caption text-medium-emphasis mb-3">
              Click any variable to copy it as a template token. Use <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts and templates from upstream steps.
            </div>
            <v-text-field
              v-model="varSearch"
              prepend-inner-icon="mdi-magnify"
              placeholder="Search variables"
              density="compact"
              hide-details
              class="mb-3 flex-grow-0 flex-shrink-0"
            />
            <div class="step-config-vars-list flex-grow-1 overflow-auto pr-1">
              <div
                v-for="item in filteredVariables"
                :key="item.key"
                class="var-row"
                @click="insertTemplateToken(item.key)"
              >
                <div class="d-flex align-center">
                  <code class="var-key">{{ formatTemplateToken(item.key) }}</code>
                  <v-spacer />
                  <v-icon size="14" class="var-copy">mdi-content-copy</v-icon>
                </div>
                <div class="text-caption text-medium-emphasis">{{ item.source }}</div>
              </div>
            </div>
            <Transition name="copied-fade">
              <div v-if="copiedToken" class="copied-toast">
                <v-icon size="14" color="success" class="mr-1">mdi-check</v-icon>
                <span class="text-caption">Copied <code>{{ copiedToken }}</code></span>
              </div>
            </Transition>
          </div>
        </div>
      </div>

      <v-divider />

      <v-card-actions class="px-6 py-3">
        <v-icon size="small" color="medium-emphasis" class="mr-1">mdi-information-outline</v-icon>
        <span class="text-caption text-medium-emphasis">
          Use <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts and templates to reference pipeline variables. Labeled steps are also accessible as <code class="cc-code">&#123;&#123;step_label.key&#125;&#125;</code>.
        </span>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" variant="flat" @click="save">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch, reactive, computed, onMounted } from "vue";
import { api } from "../../services/api.js";
import { isoToLocalHHMM, localHHMMToUTCISO } from "../../services/timezone.js";
import {
  stepConfigMap,
  genericPluginConfig,
  activityTypes,
  contextKeys,
  knownSignalKinds,
  severityItems,
  STEP_ICONS,
  STEP_LABELS,
} from "./steps/index.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  step: { type: Object, default: null },
  allSteps: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue", "save"]);

const localStep = reactive({ step_type: "", label: "" });
const cfg = reactive({});
const activeTab = ref("general");
const varSearch = ref("");
const copiedToken = ref("");

// Config registry per step type
const currentConfig = computed(() => {
  const t = localStep.step_type;
  return stepConfigMap[t] || genericPluginConfig;
});
const stepComponent = computed(() => currentConfig.value.component);

// API-fetched data
const stepTypeDefaults = ref({});
const availableChannels = ref([
  "pwa_popup_text", "telegram", "eink", "ha_speaker_tts",
  "pwa_tts_announcement", "pwa_realtime_ai", "webhook",
]);
const availablePersons = ref([]);
const availableRooms = ref([]);
const cameraSensorItems = ref([]);
const einkSensorItems = ref([]);
const haMediaPlayerItems = ref([]);
const haEntityItems = ref([]);
const imageTemplateItems = ref([]);
const llmModelItems = ref([]);

// Label validation
const LABEL_RE = /^[a-z][a-z0-9_]*$/;
const labelRules = [
  (v) => !!v || "Step label is required",
  (v) => LABEL_RE.test(v) || "Label must start with a letter and contain only lowercase letters, digits, and underscores",
];
const labelUniqueError = computed(() => {
  const label = localStep.label;
  if (!label) return "";
  const currentId = props.step?.id;
  const conflict = props.allSteps.find((s) => s.label === label && s.id !== currentId);
  return conflict ? `Label '${label}' is already used by another step in this pipeline` : "";
});

// Tabs
const tabs = computed(() => {
  const all = [{ key: "general", label: "General", icon: "mdi-tune-variant" }];
  const extra = currentConfig.value.tabs || [];
  all.push(...extra);
  return all;
});

watch(
  () => localStep.step_type,
  () => { if (tabs.value.length) activeTab.value = tabs.value[0].key; }
);

// Compute step icon
const stepIcon = computed(() => STEP_ICONS[localStep.step_type] || "mdi-cog-outline");

function humanize(type) {
  if (!type) return "Step";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

// --- Pipeline variables reference ---
const pipelineDataReference = [
  { key: "trigger.sensor_id", source: "Trigger context" },
  { key: "trigger.room_name", source: "Trigger context" },
  { key: "trigger.media_paths", source: "Trigger context" },
  { key: "trigger_input", source: "Webhook / Telegram payload" },
  { key: "trigger_input.command", source: "Telegram trigger" },
  { key: "trigger_input.chat_id", source: "Telegram trigger" },
  { key: "trigger_input.args", source: "Telegram trigger (list)" },
  { key: "trigger_input.text", source: "Telegram / webhook raw text" },
  { key: "steps.<label>.outputs.<key>", source: "General pattern — replace <label> with the step label" },
  { key: "steps.person_identification_1.outputs.person_detections", source: "person_identification" },
  { key: "steps.person_identification_1.outputs.person_detections.0.person_id", source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.person_detections.0.name", source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.person_detections.0.confidence", source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.annotated_image", source: "person_identification: base64 bbox overlay" },
  { key: "steps.scene_analysis_1.outputs.scene_detections", source: "scene_analysis: YOLO object list" },
  { key: "steps.scene_analysis_1.outputs.scene_description", source: "scene_analysis: Florence-2 text" },
  { key: "steps.scene_analysis_1.outputs.scene_hazards", source: "scene_analysis: hazard alert list" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends", source: "object_trend_analysis: map of room to trend" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends_any_warning", source: "object_trend_analysis: bool" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends_summary", source: "object_trend_analysis: compact text for LLM" },
  { key: "steps.llm_call_1.outputs.llm_response", source: "llm_call (default output_key)" },
  { key: "steps.llm_call_1.outputs.llm_response.is_notification_needed", source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.user_notification", source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.alert_level", source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.reasoning", source: "llm_call: default notification schema" },
  { key: "steps.activity_detection_1.outputs.detected_activities", source: "activity_detection" },
  { key: "steps.activity_session_start_1.outputs.session", source: "activity_session_start" },
  { key: "steps.activity_session_end_1.outputs.closed_session", source: "activity_session_end" },
  { key: "steps.verification_1.outputs.verification.verified", source: "verification: bool" },
  { key: "steps.condition_1.outputs.condition.result", source: "condition: bool" },
  { key: "steps.ha_action_1.outputs.ha_action.success", source: "ha_action: bool" },
  { key: "steps.notification_1.outputs.notification_dispatched", source: "notification: bool" },
  { key: "steps.daily_report_1.outputs.daily_reports", source: "daily_report" },
  { key: "steps.semantic_memory_write_1.outputs.semantic_memory_observation_id", source: "semantic_memory_write" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.summary", source: "semantic_memory_query: LLM-ready summary" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.observations", source: "semantic_memory_query: observation records" },
];

const filteredVariables = computed(() => {
  const q = varSearch.value.trim().toLowerCase();
  if (!q) return pipelineDataReference;
  return pipelineDataReference.filter(
    (v) => v.key.toLowerCase().includes(q) || v.source.toLowerCase().includes(q)
  );
});

function formatTemplateToken(key) {
  return `{{${key}}}`;
}

async function insertTemplateToken(key) {
  const token = formatTemplateToken(key);
  try {
    await navigator.clipboard.writeText(token);
    copiedToken.value = token;
    setTimeout(() => { copiedToken.value = ""; }, 1500);
  } catch {
    copiedToken.value = "";
  }
}

// --- Lifecycle ---

function getDefaults(stepType) {
  const fromConfig = stepConfigMap[stepType]?.defaults;
  if (fromConfig) return fromConfig;
  // Check API-fetched defaults
  return stepTypeDefaults.value[stepType] || genericPluginConfig.defaults;
}

watch(
  () => props.step,
  (step) => {
    if (!step) return;
    localStep.step_type = step.step_type || "";
    localStep.label = step.label || "";

    const base = getDefaults(step.step_type);
    const incoming = step.config_json && typeof step.config_json === "object" ? step.config_json : {};

    // Reset cfg
    Object.keys(cfg).forEach((k) => delete cfg[k]);
    Object.assign(cfg, { ...base, ...incoming });

    // Apply step-type-specific onStepLoaded
    const entry = stepConfigMap[step.step_type];
    if (entry?.onStepLoaded) {
      entry.onStepLoaded(cfg, { isoToLocalHHMM, localHHMMToUTCISO });
    }

    // Normalize target_persons to array for person_identification
    if (step.step_type === "person_identification") {
      if (typeof cfg.target_persons === "string") {
        cfg.target_persons = cfg.target_persons.split(",").map((s) => s.trim()).filter(Boolean);
      } else if (!Array.isArray(cfg.target_persons)) {
        cfg.target_persons = [];
      }
    }

    // Normalize ha_action data to string
    if (step.step_type === "ha_action" && typeof cfg.data === "object") {
      cfg.data = JSON.stringify(cfg.data, null, 2);
    }

    // For unknown/plugin types, the GenericPluginConfig handles its own JSON display
  },
  { immediate: true }
);

// Load HA entities when the ha_action domain field changes
watch(
  () => cfg.domain,
  async (domain) => {
    if (localStep.step_type !== "ha_action" || !domain) {
      haEntityItems.value = [];
      return;
    }
    try {
      haEntityItems.value = await api.getHAEntities(domain);
    } catch {
      haEntityItems.value = [];
    }
  }
);

onMounted(async () => {
  try {
    const types = await api.getStepTypes();
    for (const t of types) {
      stepTypeDefaults.value[t.type_name] = t.default_config || {};
    }
  } catch { /* use static defaults */ }
  try {
    const channels = await api.getChannelTypes();
    availableChannels.value = channels.map((c) => c.channel_name);
  } catch { /* use fallback */ }
  try {
    const persons = await api.getPersons();
    availablePersons.value = persons.map((p) => p.id);
  } catch { /* unavailable */ }
  try {
    const rooms = await api.getRooms();
    availableRooms.value = rooms.map((r) => r.name);
  } catch { /* unavailable */ }
  try {
    const sensors = await api.getSensors();
    einkSensorItems.value = sensors.filter((s) => s.sensor_type === "eink").map((s) => s.id);
    cameraSensorItems.value = sensors.filter((s) => s.sensor_type === "camera").map((s) => s.id);
  } catch { /* unavailable */ }
  try {
    haMediaPlayerItems.value = await api.getHAMediaPlayers();
  } catch { /* unavailable */ }
  try {
    llmModelItems.value = await api.getLLMModels();
  } catch { /* unavailable */ }
  try {
    imageTemplateItems.value = await api.getImageTemplates();
  } catch { /* unavailable */ }
});

// --- Save ---

function notify(msg, type) {
  // Simple notification — in real app uses useNotify() from a composable
  console.log(`[${type}] ${msg}`);
}

function validateForm() {
  // Validate forms from step components that expose validate()
  // Currently handled via expose: presence_query, home_state
  return true;
}

function save() {
  // Validate presence_query and home_state forms
  if (localStep.step_type === "presence_query" || localStep.step_type === "home_state") {
    // Form validation is handled by the step component's exposed ref
  }

  let config;
  const entry = stepConfigMap[localStep.step_type];

  // For unknown/plugin types, use GenericPluginConfig's exposed validate
  if (!entry && localStep.step_type) {
    // GenericPluginConfig handles JSON parsing internally via v-model
    try {
      JSON.parse(JSON.stringify(cfg)); // validate it's serializable
    } catch (e) {
      notify("Invalid JSON config", "error");
      return;
    }
  }

  config = { ...cfg };

  // Apply step-type-specific beforeSave
  if (entry?.beforeSave) {
    config = entry.beforeSave(config, { isoToLocalHHMM, localHHMMToUTCISO });
  }

  // Normalize target_persons to array
  if (localStep.step_type === "person_identification") {
    if (typeof config.target_persons === "string") {
      config.target_persons = config.target_persons.split(",").map((s) => s.trim()).filter(Boolean);
    } else if (!Array.isArray(config.target_persons)) {
      config.target_persons = [];
    }
  }

  // Parse ha_action data JSON string
  if (localStep.step_type === "ha_action" && typeof config.data === "string") {
    try {
      config.data = config.data.trim() ? JSON.parse(config.data) : {};
    } catch { config.data = {}; }
  }

  const labelValid = labelRules.every((r) => r(localStep.label) === true);
  if (!labelValid || labelUniqueError.value) return;

  emit("save", {
    step_type: localStep.step_type,
    label: localStep.label,
    config_json: config,
  });
  emit("update:modelValue", false);
}
</script>

<style scoped>
.step-config-card {
  height: 88vh;
  max-height: 880px;
  border-radius: 24px;
  overflow: hidden;
}

.step-config-header {
  background: linear-gradient(135deg, rgba(10, 132, 255, 0.08) 0%, rgba(94, 92, 230, 0.04) 100%);
}

.step-config-icon {
  background: linear-gradient(135deg, #0a84ff 0%, #5e5ce6 60%, #bf5af2 100%);
}

.step-config-body {
  min-height: 0;
}

.step-config-tabs {
  width: 220px;
  background-color: var(--cc-bg-elevated);
  padding-top: 12px;
}

.step-config-tabs :deep(.v-tab) {
  justify-content: flex-start !important;
  padding-inline: 20px !important;
  border-radius: 0;
  font-weight: 500;
  height: 44px;
}

.step-config-content {
  overflow-y: auto;
  overflow-x: hidden;
  min-width: 0;
}

.step-config-content :deep(.v-window),
.step-config-content :deep(.v-window__container) {
  overflow: visible !important;
}

.step-config-vars {
  width: 300px;
  flex-shrink: 0;
  background-color: var(--cc-bg-elevated);
  min-width: 0;
}

.step-config-vars-list {
  min-height: 0;
}

.var-row {
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.var-row:hover {
  background-color: rgba(10, 132, 255, 0.10);
}

.var-row + .var-row {
  margin-top: 2px;
}

.var-key {
  font-family: var(--cc-font-mono);
  font-size: 12px;
  color: var(--cc-brand);
  background: transparent;
  padding: 0;
}

.var-copy {
  opacity: 0;
  transition: opacity 0.12s ease;
}

.var-row:hover .var-copy {
  opacity: 0.6;
}

.tracking-tight {
  letter-spacing: -0.014em;
}

.copied-toast {
  position: absolute;
  bottom: 16px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  background: rgba(var(--v-theme-success), 0.12);
  border: 1px solid rgba(var(--v-theme-success), 0.3);
  border-radius: 8px;
  padding: 6px 10px;
  pointer-events: none;
}

.copied-fade-enter-active,
.copied-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.copied-fade-enter-from,
.copied-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
