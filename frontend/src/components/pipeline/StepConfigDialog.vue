<template>
  <!-- Extra-large sectioned editor: one section per config tab, with the pipeline variables
       as a reference panel beside them. -->
  <AppDialog
    v-model:section="activeTab"
    :model-value="modelValue"
    size="xl"
    persistent
    :icon="stepIcon"
    label="Configure Step"
    :title="humanize(localStep.step_type)"
    :sections="tabs"
    confirm-label="Save"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="save"
  >
    <template v-for="tabItem in tabs" :key="tabItem.key" #[`section-${tabItem.key}`]>
      <!-- General tab: step label + step-type config -->
      <v-text-field
        v-if="tabItem.key === 'general'"
        v-model="localStep.label"
        label="Step Label"
        hint="Used as the key in pipeline_data.steps — must be unique, lowercase, letters/digits/underscores only"
        persistent-hint
        :rules="labelRules"
        :error-messages="labelUniqueError"
        class="mb-5"
      />

      <KeepAlive>
        <component
          :is="stepComponent"
          :key="`${localStep.step_type}_${tabItem.key}`"
          :model-value="cfg"
          :tab="tabItem.key"
          :schema="currentStepSchema"
          :all-steps="allSteps"
          :available-persons="availablePersons"
          :available-rooms="availableRooms"
          :available-channels="availableChannels"
          :camera-sensor-items="cameraSensorItems"
          :cts-camera-items="ctsCameraItems"
          :ha-entity-items="haEntityItems"
          :ha-media-player-items="haMediaPlayerItems"
          :eink-sensor-items="einkSensorItems"
          :image-template-items="imageTemplateItems"
          :llm-model-items="llmModelItems"
          :activity-types="activityTypes"
          :context-keys="contextKeys"
          :known-signal-kinds="knownSignalKinds"
          :severity-items="severityItems"
          @update:model-value="Object.assign(cfg, $event)"
        />
      </KeepAlive>
    </template>

    <!-- Pipeline Variables reference panel -->
    <template #trailing>
      <div class="step-config-vars d-flex flex-column flex-grow-1">
        <div class="d-flex align-center mb-3">
          <v-icon size="small" class="mr-2" color="primary">mdi-code-braces</v-icon>
          <div class="text-subtitle-2 font-weight-bold">Pipeline Variables</div>
        </div>
        <div class="text-caption text-medium-emphasis mb-3">
          Click any variable to copy it as a template token. Use
          <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts and templates from
          upstream steps.
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
            :key="item.id"
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
            <span class="text-caption"
              >Copied <code>{{ copiedToken }}</code></span
            >
          </div>
        </Transition>
      </div>
    </template>

    <template #hint>
      <span class="text-caption text-medium-emphasis">
        Use <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts and templates to
        reference pipeline variables. Labeled steps are also accessible as
        <code class="cc-code">&#123;&#123;step_label.key&#125;&#125;</code>.
      </span>
    </template>
  </AppDialog>
</template>

<script setup>
import { ref, watch, reactive, computed, onMounted, provide } from "vue";
import { api } from "../../services/api.js";
import { cts } from "../../services/cts.js";
import { isoToLocalHHMM, localHHMMToUTCISO } from "../../services/timezone.js";
import { useNotify } from "../../composables/useNotify.js";
import AppDialog from "../common/AppDialog.vue";
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
const stepTypeSchemas = ref({});
const dataKeys = ref({ trigger: [], system: [], step_outputs: {} });
const currentStepSchema = computed(() => stepTypeSchemas.value[localStep.step_type] || {});
const availableChannels = ref([
  "pwa_popup_text",
  "telegram",
  "eink",
  "ha_speaker_tts",
  "pwa_tts_announcement",
  "pwa_realtime_ai",
  "webhook",
]);
const availablePersons = ref([]);
const availableRooms = ref([]);
const cameraSensorItems = ref([]);
const ctsCameraItems = ref([]);
const einkSensorItems = ref([]);
const haMediaPlayerItems = ref([]);
const haEntityItems = ref([]);
const imageTemplateItems = ref([]);
const llmModelItems = ref([]);

// Label validation
const LABEL_RE = /^[a-z][a-z0-9_]*$/;
const labelRules = [
  (v) => !!v || "Step label is required",
  (v) =>
    LABEL_RE.test(v) ||
    "Label must start with a letter and contain only lowercase letters, digits, and underscores",
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
  () => {
    if (tabs.value.length) activeTab.value = tabs.value[0].key;
  },
);

// Compute step icon
const stepIcon = computed(() => STEP_ICONS[localStep.step_type] || "mdi-cog-outline");

// Rule context — step labels and their output schemas — provided to TemplateInput
// components anywhere in the step config subtree via inject('pipelineRuleContext').
const ruleContext = computed(() => {
  const labels = props.allSteps.map((s) => s.label).filter(Boolean);
  const stepOutputs = {};
  for (const s of props.allSteps) {
    const schema = stepTypeSchemas.value[s.step_type];
    if (s.label && schema?.output_schema?.properties) {
      stepOutputs[s.label] = schema.output_schema;
    }
  }
  return { labels, stepOutputs };
});
provide("pipelineRuleContext", ruleContext);

function humanize(type) {
  if (!type) return "Step";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// --- Pipeline variables reference (computed from API data) ---

function _buildPipelineReference() {
  const entries = [];
  // Trigger and system vars from data-keys API
  for (const v of dataKeys.value.trigger || []) {
    entries.push({ key: v.key, source: v.description || "Trigger context" });
  }
  for (const v of dataKeys.value.system || []) {
    entries.push({ key: v.key, source: v.description || "System" });
  }
  // General pattern
  entries.push({ key: "steps.<label>.outputs.<key>", source: "General pattern" });
  // Per-step-type output vars from data-keys API
  const stepOutputs = dataKeys.value.step_outputs || {};
  for (const [stepType, outputSchema] of Object.entries(stepOutputs)) {
    const props = outputSchema.properties || {};
    for (const [propName, propSchema] of Object.entries(props)) {
      entries.push({
        key: `steps.<label>.outputs.${propName}`,
        source: `${stepType}: ${propSchema.description || propName}`,
      });
    }
  }
  // Per-step instance entries for current pipeline's labels
  for (const s of props.allSteps || []) {
    const stepMetaSchema = stepTypeSchemas.value[s.step_type];
    if (!stepMetaSchema?.output_schema?.properties) continue;
    for (const [propName] of Object.entries(stepMetaSchema.output_schema.properties)) {
      entries.push({
        key: `steps.${s.label}.outputs.${propName}`,
        source: `${s.label} (${s.step_type})`,
      });
    }
  }
  // Step types share output names (count, skipped, reason), so one token can appear once per
  // source; a row is identified by both, and an exact repeat is dropped.
  const unique = new Map();
  for (const entry of entries) {
    const id = `${entry.key}::${entry.source}`;
    if (!unique.has(id)) unique.set(id, { ...entry, id });
  }
  return [...unique.values()];
}

const pipelineVariableEntries = computed(() => _buildPipelineReference());

const filteredVariables = computed(() => {
  const q = varSearch.value.trim().toLowerCase();
  if (!q) return pipelineVariableEntries.value;
  return pipelineVariableEntries.value.filter(
    (v) => v.key.toLowerCase().includes(q) || v.source.toLowerCase().includes(q),
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
    setTimeout(() => {
      copiedToken.value = "";
    }, 1500);
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
    const incoming =
      step.config_json && typeof step.config_json === "object" ? step.config_json : {};

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
        cfg.target_persons = cfg.target_persons
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
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
  { immediate: true },
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
  },
);

onMounted(async () => {
  try {
    const types = await api.getStepTypes();
    for (const t of types) {
      stepTypeDefaults.value[t.type_name] = t.default_config || {};
      stepTypeSchemas.value[t.type_name] = t;
    }
  } catch {
    /* use static defaults */
  }
  try {
    dataKeys.value = await api.getDataKeys();
  } catch {
    /* use static reference */
  }
  try {
    const channels = await api.getChannelTypes();
    availableChannels.value = channels.map((c) => c.channel_name);
  } catch {
    /* use fallback */
  }
  try {
    const persons = await api.getPersons();
    availablePersons.value = persons.map((p) => p.id);
  } catch {
    /* unavailable */
  }
  try {
    const rooms = await api.getRooms();
    availableRooms.value = rooms.map((r) => r.name);
  } catch {
    /* unavailable */
  }
  try {
    const sensors = await api.getSensors();
    einkSensorItems.value = sensors.filter((s) => s.sensor_type === "eink").map((s) => s.id);
    cameraSensorItems.value = sensors.filter((s) => s.sensor_type === "camera").map((s) => s.id);
  } catch {
    /* unavailable */
  }
  try {
    // CTS camera roster (distinct from reCamera sensors). Empty when CTS is
    // disabled; the dropdowns degrade to free text entry.
    const ctsCameras = await cts.getCameras();
    ctsCameraItems.value = (ctsCameras || []).map((c) => c.id);
  } catch {
    /* CTS disabled or unavailable */
  }
  try {
    haMediaPlayerItems.value = await api.getHAMediaPlayers();
  } catch {
    /* unavailable */
  }
  try {
    llmModelItems.value = await api.getLLMModels();
  } catch {
    /* unavailable */
  }
  try {
    imageTemplateItems.value = await api.getImageTemplates();
  } catch {
    /* unavailable */
  }
});

// --- Save ---

const { notify: notifyUser } = useNotify();

function notify(msg, type) {
  notifyUser(msg, type);
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
    } catch (_e) {
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
      config.target_persons = config.target_persons
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else if (!Array.isArray(config.target_persons)) {
      config.target_persons = [];
    }
  }

  // Parse ha_action data JSON string
  if (localStep.step_type === "ha_action" && typeof config.data === "string") {
    try {
      config.data = config.data.trim() ? JSON.parse(config.data) : {};
    } catch {
      config.data = {};
    }
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
/* The copied-token toast is positioned against the variables panel. */
.step-config-vars {
  position: relative;
  min-height: 0;
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
  background-color: var(--cc-brand-softer);
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

.copied-toast {
  position: absolute;
  bottom: 16px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  background: var(--cc-bg-elevated);
  border: 1px solid var(--cc-divider-strong);
  box-shadow: var(--cc-shadow-sm);
  border-radius: 8px;
  padding: 6px 10px;
  pointer-events: none;
}

.copied-fade-enter-active,
.copied-fade-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.copied-fade-enter-from,
.copied-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
