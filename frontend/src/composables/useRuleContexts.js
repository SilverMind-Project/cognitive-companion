import { ref, watch } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

export const CONTEXT_TYPE_ITEMS = [
  { label: "Room", value: "room" },
  { label: "Time Range", value: "time_range" },
  { label: "Day of Week", value: "day_of_week" },
  { label: "Person Presence", value: "person_presence" },
  { label: "Person Activity", value: "person_activity" },
  { label: "Home State", value: "home_state" },
  { label: "Presence Dwell", value: "presence_dwell" },
  { label: "Presence Status", value: "presence_status" },
  { label: "Scene Contains", value: "scene_contains" },
  { label: "Person Movement (Memory)", value: "person_movement_memory" },
  { label: "Room Transition", value: "room_transition" },
  { label: "Scene Trend", value: "scene_trend" },
  { label: "Dementia Signal", value: "dementia_signal" },
];

export const DAY_ITEMS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

export const ACTIVITY_TYPE_ITEMS = [
  "eating",
  "sleeping",
  "medication",
  "bathing",
  "walking",
  "watching_tv",
  "reading",
  "exercising",
  "cooking",
  "socializing",
];

export const DEMENTIA_SIGNAL_KINDS = [
  "pacing",
  "room_revisit_rate",
  "bathroom_dwell_anomaly",
  "sundowning_index",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
  "fall_suspected",
];

const JSON_FORM_CONTEXT_TYPES = [
  "room",
  "time_range",
  "day_of_week",
  "person_presence",
  "person_activity",
  "scene_contains",
  "person_movement_memory",
];

export function ctxIcon(type) {
  const map = {
    room: { icon: "mdi-floor-plan", color: "primary" },
    time_range: { icon: "mdi-clock-outline", color: "orange" },
    day_of_week: { icon: "mdi-calendar-week", color: "purple" },
    person_presence: { icon: "mdi-account-check", color: "success" },
    person_activity: { icon: "mdi-run", color: "info" },
    home_state: { icon: "mdi-home-variant", color: "indigo" },
    presence_status: { icon: "mdi-map-marker-radius", color: "primary" },
    presence_dwell: { icon: "mdi-timer-sand", color: "deep-purple" },
    scene_contains: { icon: "mdi-image-search", color: "teal" },
    person_movement_memory: { icon: "mdi-map-marker-distance", color: "deep-orange" },
  };
  return map[type] || { icon: "mdi-filter", color: "grey" };
}

export function ctxSummary(ctx) {
  const c = ctx.config_json || {};
  switch (ctx.context_type) {
    case "room":
      return c.room_name || "Any room";
    case "time_range":
      return `${c.start_time || "?"} - ${c.end_time || "?"}`;
    case "day_of_week":
      return Array.isArray(c.days) ? c.days.join(", ") : JSON.stringify(c);
    case "person_presence":
      return `${c.person_id || "any person"} is ${c.status || "?"}${c.room_name ? " in " + c.room_name : ""}${c.use_semantic_memory ? " (semantic)" : ""}`;
    case "person_activity":
      return `${c.person_id || "any person"}: ${c.activity_type || "?"}`;
    case "home_state":
      return `${c.person_id || "any person"} state = ${c.state || "?"}`;
    case "presence_status":
      return (
        `${c.person_id || "any person"}: ${c.status || "?"}` +
        (c.room_name ? ` in ${c.room_name}` : "")
      );
    case "presence_dwell":
      return `${c.person_id || "any person"}: ${c.status || "any status"} ≥ ${c.min_minutes || "?"} min`;
    case "scene_contains": {
      const parts = [];
      if (c.objects_any?.length) parts.push(`objects: ${c.objects_any.join(", ")}`);
      if (c.hazard_flags_any?.length) parts.push(`hazards: ${c.hazard_flags_any.join(", ")}`);
      return parts.length ? parts.join(" + ") : "Any scene";
    }
    case "person_movement_memory":
      return `${c.person_id || "any person"}: ${c.semantic || "any"}${c.to_room_id ? " → " + c.to_room_id : ""}`;
    default:
      return JSON.stringify(c);
  }
}

function seedCtxConfig(type) {
  switch (type) {
    case "home_state":
      return { state: "at_home" };
    case "presence_status":
      return { status: "present_room" };
    case "presence_dwell":
      return { status: "", min_minutes: 5 };
    default:
      return {};
  }
}

/** Context-filter dialog state and CRUD for a rule's context list. */
export function useRuleContexts(ruleId, { onChanged } = {}) {
  const { notify } = useNotify();

  const ctxDialog = ref(false);
  const ctxForm = ref({ context_type: "room", config: {}, negate: false });
  const ctxConfigStr = ref("{}");

  function openCtxDialog() {
    ctxForm.value = { context_type: "room", config: {}, negate: false };
    ctxConfigStr.value = "{}";
    ctxDialog.value = true;
  }

  async function addContext() {
    try {
      let config;
      const t = ctxForm.value.context_type;
      if (JSON_FORM_CONTEXT_TYPES.includes(t)) {
        config = { ...ctxForm.value.config };
      } else {
        config = JSON.parse(ctxConfigStr.value);
      }
      await api.addRuleContext(ruleId.value, {
        context_type: t,
        config_json: config,
        negate: ctxForm.value.negate || false,
      });
      ctxDialog.value = false;
      await onChanged?.();
      notify("Context added");
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function deleteContext(ctxId) {
    try {
      await api.deleteRuleContext(ruleId.value, ctxId);
      await onChanged?.();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  // Seed default config when context_type changes in the filter dialog.
  watch(
    () => ctxForm.value.context_type,
    (type) => {
      const defaults = seedCtxConfig(type);
      if (Object.keys(defaults).length > 0) {
        for (const [key, value] of Object.entries(defaults)) {
          if (ctxForm.value.config[key] === undefined || ctxForm.value.config[key] === null) {
            ctxForm.value.config[key] = value;
          }
        }
      }
    },
  );

  return {
    ctxDialog,
    ctxForm,
    ctxConfigStr,
    openCtxDialog,
    addContext,
    deleteContext,
  };
}
