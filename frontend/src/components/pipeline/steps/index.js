// Registry mapping step_type -> component + metadata
// Backend step handlers: backend/steps/builtin/<name>.py

import WaitConfig, {
  stepDefaults as waitDefaults,
  stepTabs as waitTabs,
  chips as waitChips,
} from "./WaitConfig.vue";
import HAActionConfig, {
  stepDefaults as haDefaults,
  stepTabs as haTabs,
  chips as haChips,
} from "./HAActionConfig.vue";
import ObjectTrendAnalysisConfig, {
  stepDefaults as otaDefaults,
  stepTabs as otaTabs,
  chips as otaChips,
} from "./ObjectTrendAnalysisConfig.vue";
import DailyReportConfig, {
  stepDefaults as drDefaults,
  stepTabs as drTabs,
} from "./DailyReportConfig.vue";
import HomeStateConfig, {
  stepDefaults as hsDefaults,
  stepTabs as hsTabs,
} from "./HomeStateConfig.vue";
import PersonIdentificationConfig, {
  stepDefaults as piDefaults,
  stepTabs as piTabs,
  chips as piChips,
} from "./PersonIdentificationConfig.vue";
import SceneAnalysisConfig, {
  stepDefaults as saDefaults,
  stepTabs as saTabs,
  chips as saChips,
} from "./SceneAnalysisConfig.vue";
import ActivityDetectionConfig, {
  stepDefaults as adDefaults,
  stepTabs as adTabs,
  chips as adChips,
} from "./ActivityDetectionConfig.vue";
import ActivitySessionStartConfig, {
  stepDefaults as assDefaults,
  stepTabs as assTabs,
  chips as assChips,
} from "./ActivitySessionStartConfig.vue";
import ActivitySessionEndConfig, {
  stepDefaults as aseDefaults,
  stepTabs as aseTabs,
  chips as aseChips,
} from "./ActivitySessionEndConfig.vue";
import PresenceQueryConfig, {
  stepDefaults as pqDefaults,
  stepTabs as pqTabs,
} from "./PresenceQueryConfig.vue";
import SemanticMemoryWriteConfig, {
  stepDefaults as smwDefaults,
  stepTabs as smwTabs,
  chips as smwChips,
} from "./SemanticMemoryWriteConfig.vue";
import SemanticMemoryQueryConfig, {
  stepDefaults as smqDefaults,
  stepTabs as smqTabs,
  chips as smqChips,
} from "./SemanticMemoryQueryConfig.vue";
import LLMCallConfig, {
  stepDefaults as llmDefaults,
  stepTabs as llmTabs,
  beforeSave as llmBeforeSave,
  onStepLoaded as llmOnStepLoaded,
  chips as llmChips,
} from "./LLMCallConfig.vue";
import NotificationConfig, {
  stepDefaults as notifDefaults,
  stepTabs as notifTabs,
  beforeSave as notifBeforeSave,
  onStepLoaded as notifOnStepLoaded,
  chips as notifChips,
} from "./NotificationConfig.vue";
import ConditionConfig, {
  stepDefaults as condDefaults,
  stepTabs as condTabs,
  chips as condChips,
} from "./ConditionConfig.vue";
import VerificationConfig, {
  stepDefaults as verDefaults,
  stepTabs as verTabs,
  beforeSave as verBeforeSave,
  onStepLoaded as verOnStepLoaded,
  chips as verChips,
} from "./VerificationConfig.vue";
import InteractivePromptConfig, {
  stepDefaults as ipDefaults,
  stepTabs as ipTabs,
} from "./InteractivePromptConfig.vue";
import GenericPluginConfig, { stepTabs as genericTabs } from "./GenericPluginConfig.vue";
import MediaWindowPollConfig, {
  stepDefaults as mwpDefaults,
  stepTabs as mwpTabs,
} from "./MediaWindowPollConfig.vue";
import InfoCardConfig, {
  stepDefaults as infoCardDefaults,
  stepTabs as infoCardTabs,
} from "./InfoCardConfig.vue";
import ImageCropConfig, {
  stepDefaults as imageCropDefaults,
  stepTabs as imageCropTabs,
  chips as imageCropChips,
} from "./ImageCropConfig.vue";
import GateVerdictConfig, {
  stepDefaults as gateVerdictDefaults,
  stepTabs as gateVerdictTabs,
} from "./GateVerdictConfig.vue";
import RegionPresenceConfig, {
  stepDefaults as regionPresenceDefaults,
  stepTabs as regionPresenceTabs,
  chips as regionPresenceChips,
} from "./RegionPresenceConfig.vue";
import SignalEmitConfig, {
  stepDefaults as signalEmitDefaults,
  stepTabs as signalEmitTabs,
  beforeSave as signalEmitBeforeSave,
  onStepLoaded as signalEmitOnStepLoaded,
  chips as signalEmitChips,
} from "./SignalEmitConfig.vue";
import vocabularies from "@/generated/vocabularies.json";
import { ALERT_COLORS, chip, truncate } from "./stepMeta.js";

export const stepConfigMap = {
  wait: { component: WaitConfig, defaults: waitDefaults, tabs: waitTabs, chips: waitChips },
  ha_action: { component: HAActionConfig, defaults: haDefaults, tabs: haTabs, chips: haChips },
  object_trend_analysis: {
    component: ObjectTrendAnalysisConfig,
    defaults: otaDefaults,
    tabs: otaTabs,
    chips: otaChips,
  },
  daily_report: { component: DailyReportConfig, defaults: drDefaults, tabs: drTabs },
  home_state: { component: HomeStateConfig, defaults: hsDefaults, tabs: hsTabs },
  person_identification: {
    component: PersonIdentificationConfig,
    defaults: piDefaults,
    tabs: piTabs,
    chips: piChips,
  },
  scene_analysis: {
    component: SceneAnalysisConfig,
    defaults: saDefaults,
    tabs: saTabs,
    chips: saChips,
  },
  activity_detection: {
    component: ActivityDetectionConfig,
    defaults: adDefaults,
    tabs: adTabs,
    chips: adChips,
  },
  activity_session_start: {
    component: ActivitySessionStartConfig,
    defaults: assDefaults,
    tabs: assTabs,
    chips: assChips,
  },
  activity_session_end: {
    component: ActivitySessionEndConfig,
    defaults: aseDefaults,
    tabs: aseTabs,
    chips: aseChips,
  },
  presence_query: { component: PresenceQueryConfig, defaults: pqDefaults, tabs: pqTabs },
  semantic_memory_write: {
    component: SemanticMemoryWriteConfig,
    defaults: smwDefaults,
    tabs: smwTabs,
    chips: smwChips,
  },
  semantic_memory_query: {
    component: SemanticMemoryQueryConfig,
    defaults: smqDefaults,
    tabs: smqTabs,
    chips: smqChips,
  },
  llm_call: {
    component: LLMCallConfig,
    defaults: llmDefaults,
    tabs: llmTabs,
    beforeSave: llmBeforeSave,
    onStepLoaded: llmOnStepLoaded,
    chips: llmChips,
  },
  notification: {
    component: NotificationConfig,
    defaults: notifDefaults,
    tabs: notifTabs,
    beforeSave: notifBeforeSave,
    onStepLoaded: notifOnStepLoaded,
    chips: notifChips,
  },
  condition: {
    component: ConditionConfig,
    defaults: condDefaults,
    tabs: condTabs,
    chips: condChips,
  },
  verification: {
    component: VerificationConfig,
    defaults: verDefaults,
    tabs: verTabs,
    beforeSave: verBeforeSave,
    onStepLoaded: verOnStepLoaded,
    chips: verChips,
  },
  interactive_prompt: { component: InteractivePromptConfig, defaults: ipDefaults, tabs: ipTabs },
  guided_task_start: {
    component: GenericPluginConfig,
    defaults: { require_presence: true, dedupe_hours: 0 },
    tabs: genericTabs,
  },
  media_window_poll: { component: MediaWindowPollConfig, defaults: mwpDefaults, tabs: mwpTabs },
  info_card: { component: InfoCardConfig, defaults: infoCardDefaults, tabs: infoCardTabs },
  image_crop: {
    component: ImageCropConfig,
    defaults: imageCropDefaults,
    tabs: imageCropTabs,
    chips: imageCropChips,
  },
  gate_verdict: {
    component: GateVerdictConfig,
    defaults: gateVerdictDefaults,
    tabs: gateVerdictTabs,
  },
  region_presence: {
    component: RegionPresenceConfig,
    defaults: regionPresenceDefaults,
    tabs: regionPresenceTabs,
    chips: regionPresenceChips,
  },
  quiz_start: { component: GenericPluginConfig, defaults: {}, tabs: genericTabs },
  media_presign: {
    component: GenericPluginConfig,
    defaults: { object_names_key: [], retention_minutes: 240, output_key: "presigned_images" },
    tabs: genericTabs,
  },
  novelty_gate: {
    component: GenericPluginConfig,
    defaults: {
      embedding_key: "scene_embedding",
      scope: "{{rule}}:{{camera}}",
      min_distance: null,
      ttl_minutes: 120,
    },
    tabs: genericTabs,
  },
  signal_emit: {
    component: SignalEmitConfig,
    defaults: signalEmitDefaults,
    tabs: signalEmitTabs,
    beforeSave: signalEmitBeforeSave,
    onStepLoaded: signalEmitOnStepLoaded,
    chips: signalEmitChips,
  },
};
import SchemaForm from "./_shared/SchemaForm.vue";

export const genericPluginConfig = {
  component: SchemaForm,
  defaults: {},
  tabs: [],
};

// Shared constants
export const activityTypes = [
  "eating",
  "drinking",
  "cooking",
  "meal_prep",
  "sleeping",
  "resting",
  "bathing",
  "grooming",
  "toileting",
  "dressing",
  "medication",
  "medication_morning",
  "medication_evening",
  "blood_pressure_check",
  "glucose_check",
  "walking",
  "exercising",
  "stretching",
  "physical_therapy",
  "watching_tv",
  "reading",
  "socializing",
  "phone_call",
  "gardening",
  "left_stove_on",
  "door_opened",
  "fall_detected",
  "bathroom_occupancy",
  "meal_lunch",
  "meal_dinner",
  "meal_breakfast",
];

export const contextKeys = [
  "vision_response",
  "person_detections",
  "logic_response",
  "translation",
  "detected_activities",
  "annotated_image",
  "verification",
  "condition",
  "scene_memory_observation_id",
  "semantic_memory_observation_id",
  "semantic_memory_movement_ids",
  "memory_context",
];

export const knownSignalKinds = vocabularies.signal_kinds;

// Thin dispatcher: each step's config-detail chips are co-located with its config component
// (stepConfigMap[type].chips) rather than living in one 126-line per-type if-chain.
export function buildStepDetailChips(step) {
  const cfg = step.config_json;
  if (!cfg || typeof cfg !== "object") return [];
  const entries =
    stepConfigMap[step.step_type]?.chips?.(cfg, { chip, truncate, ALERT_COLORS }) ?? [];
  return entries.map((c, i) => ({ ...c, key: i }));
}

export const severityItems = [
  { label: "Info", value: "info" },
  { label: "Warning", value: "warning" },
  { label: "Emergency", value: "emergency" },
];

export { STEP_ICONS, STEP_LABELS } from "./stepMeta.js";
