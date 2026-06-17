// Registry mapping step_type -> component + metadata
// Backend step handlers: backend/steps/builtin/<name>.py

import WaitConfig, { stepDefaults as waitDefaults, stepTabs as waitTabs } from "./WaitConfig.vue";
import HAActionConfig, { stepDefaults as haDefaults, stepTabs as haTabs } from "./HAActionConfig.vue";
import ObjectTrendAnalysisConfig, { stepDefaults as otaDefaults, stepTabs as otaTabs } from "./ObjectTrendAnalysisConfig.vue";
import DailyReportConfig, { stepDefaults as drDefaults, stepTabs as drTabs } from "./DailyReportConfig.vue";
import HomeStateConfig, { stepDefaults as hsDefaults, stepTabs as hsTabs } from "./HomeStateConfig.vue";
import PersonIdentificationConfig, { stepDefaults as piDefaults, stepTabs as piTabs } from "./PersonIdentificationConfig.vue";
import SceneAnalysisConfig, { stepDefaults as saDefaults, stepTabs as saTabs } from "./SceneAnalysisConfig.vue";
import ActivityDetectionConfig, { stepDefaults as adDefaults, stepTabs as adTabs } from "./ActivityDetectionConfig.vue";
import ActivitySessionStartConfig, { stepDefaults as assDefaults, stepTabs as assTabs } from "./ActivitySessionStartConfig.vue";
import ActivitySessionEndConfig, { stepDefaults as aseDefaults, stepTabs as aseTabs } from "./ActivitySessionEndConfig.vue";
import PresenceQueryConfig, { stepDefaults as pqDefaults, stepTabs as pqTabs } from "./PresenceQueryConfig.vue";
import SemanticMemoryWriteConfig, { stepDefaults as smwDefaults, stepTabs as smwTabs } from "./SemanticMemoryWriteConfig.vue";
import SemanticMemoryQueryConfig, { stepDefaults as smqDefaults, stepTabs as smqTabs } from "./SemanticMemoryQueryConfig.vue";
import LLMCallConfig, { stepDefaults as llmDefaults, stepTabs as llmTabs, beforeSave as llmBeforeSave, onStepLoaded as llmOnStepLoaded } from "./LLMCallConfig.vue";
import NotificationConfig, { stepDefaults as notifDefaults, stepTabs as notifTabs, beforeSave as notifBeforeSave, onStepLoaded as notifOnStepLoaded } from "./NotificationConfig.vue";
import ConditionConfig, { stepDefaults as condDefaults, stepTabs as condTabs } from "./ConditionConfig.vue";
import VerificationConfig, { stepDefaults as verDefaults, stepTabs as verTabs, beforeSave as verBeforeSave, onStepLoaded as verOnStepLoaded } from "./VerificationConfig.vue";
import InteractivePromptConfig, { stepDefaults as ipDefaults, stepTabs as ipTabs } from "./InteractivePromptConfig.vue";
import GenericPluginConfig, { stepDefaults as genericDefaults, stepTabs as genericTabs } from "./GenericPluginConfig.vue";
import MediaWindowPollConfig, { stepDefaults as mwpDefaults, stepTabs as mwpTabs } from "./MediaWindowPollConfig.vue";
import InfoCardConfig, { stepDefaults as infoCardDefaults, stepTabs as infoCardTabs } from "./InfoCardConfig.vue";
import ImageCropConfig, { stepDefaults as imageCropDefaults, stepTabs as imageCropTabs } from "./ImageCropConfig.vue";

export const stepConfigMap = {
  wait:                { component: WaitConfig,                defaults: waitDefaults,    tabs: waitTabs },
  ha_action:           { component: HAActionConfig,            defaults: haDefaults,      tabs: haTabs },
  object_trend_analysis: { component: ObjectTrendAnalysisConfig, defaults: otaDefaults,   tabs: otaTabs },
  daily_report:        { component: DailyReportConfig,         defaults: drDefaults,      tabs: drTabs },
  home_state:          { component: HomeStateConfig,           defaults: hsDefaults,      tabs: hsTabs },
  person_identification: { component: PersonIdentificationConfig, defaults: piDefaults,  tabs: piTabs },
  scene_analysis:      { component: SceneAnalysisConfig,       defaults: saDefaults,      tabs: saTabs },
  activity_detection:  { component: ActivityDetectionConfig,   defaults: adDefaults,      tabs: adTabs },
  activity_session_start: { component: ActivitySessionStartConfig, defaults: assDefaults, tabs: assTabs },
  activity_session_end:   { component: ActivitySessionEndConfig, defaults: aseDefaults,   tabs: aseTabs },
  presence_query:      { component: PresenceQueryConfig,       defaults: pqDefaults,      tabs: pqTabs },
  semantic_memory_write: { component: SemanticMemoryWriteConfig, defaults: smwDefaults,   tabs: smwTabs },
  semantic_memory_query: { component: SemanticMemoryQueryConfig, defaults: smqDefaults,   tabs: smqTabs },
  llm_call:            { component: LLMCallConfig,             defaults: llmDefaults,     tabs: llmTabs,    beforeSave: llmBeforeSave,    onStepLoaded: llmOnStepLoaded },
  notification:        { component: NotificationConfig,        defaults: notifDefaults,   tabs: notifTabs,  beforeSave: notifBeforeSave,  onStepLoaded: notifOnStepLoaded },
  condition:           { component: ConditionConfig,           defaults: condDefaults,    tabs: condTabs },
  verification:        { component: VerificationConfig,        defaults: verDefaults,     tabs: verTabs,    beforeSave: verBeforeSave,    onStepLoaded: verOnStepLoaded },
  interactive_prompt:  { component: InteractivePromptConfig,   defaults: ipDefaults,      tabs: ipTabs },
  guided_task_start:   { component: GenericPluginConfig,        defaults: { require_presence: true, dedupe_hours: 0 }, tabs: genericTabs },
  media_window_poll:   { component: MediaWindowPollConfig,     defaults: mwpDefaults,     tabs: mwpTabs },
  info_card:           { component: InfoCardConfig,            defaults: infoCardDefaults, tabs: infoCardTabs },
  image_crop:          { component: ImageCropConfig,           defaults: imageCropDefaults, tabs: imageCropTabs },
};
import SchemaForm from "./_shared/SchemaForm.vue";

export const genericPluginConfig = {
  component: SchemaForm,
  defaults: {},
  tabs: [],
};

// Shared constants
export const activityTypes = [
  "eating", "drinking", "cooking", "meal_prep",
  "sleeping", "resting", "bathing", "grooming", "toileting", "dressing",
  "medication", "medication_morning", "medication_evening",
  "blood_pressure_check", "glucose_check",
  "walking", "exercising", "stretching", "physical_therapy",
  "watching_tv", "reading", "socializing", "phone_call", "gardening",
  "left_stove_on", "door_opened", "fall_detected", "bathroom_occupancy",
  "meal_lunch", "meal_dinner", "meal_breakfast",
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

export const knownSignalKinds = [
  "bathroom_dwell_anomaly",
  "pacing",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
  "sundowning_index",
  "fall_suspected",
];

export const severityItems = [
  { label: "Info", value: "info" },
  { label: "Warning", value: "warning" },
  { label: "Emergency", value: "emergency" },
];

export { STEP_ICONS, STEP_LABELS } from "./stepMeta.js";
