import vocabularies from "@/generated/vocabularies.json";

// Derived from the backend-canonical step registry export rather than hand-copied, so a new
// or renamed step type cannot silently drift out of the palette label/icon maps (C8).
export const STEP_LABELS = Object.fromEntries(
  vocabularies.step_types.map((s) => [s.type_name, s.display_name]),
);

export const STEP_ICONS = Object.fromEntries(
  vocabularies.step_types.map((s) => [s.type_name, s.icon]),
);

export const STEP_DOT_COLORS = {
  activity_detection: "indigo",
  activity_session_start: "green",
  activity_session_end: "red",
  condition: "blue-grey",
  daily_report: "indigo",
  gate_verdict: "green",
  ha_action: "blue",
  home_state: "blue",
  image_crop: "teal",
  guided_task_start: "success",
  info_card: "cyan",
  interactive_prompt: "cyan",
  knowledge_query: "info",
  llm_call: "purple",
  media_presign: "teal",
  media_window_poll: "teal",
  notification: "orange",
  novelty_gate: "teal",
  object_trend_analysis: "teal",
  person_identification: "indigo",
  presence_query: "blue",
  quiz_start: "secondary",
  region_presence: "green",
  scene_analysis: "teal",
  semantic_memory_query: "teal",
  semantic_memory_write: "indigo",
  signal_emit: "orange",
  verification: "green",
  wait: "amber",
};

export const ALERT_COLORS = {
  emergency: "red",
  warning: "orange",
  info: "blue",
  reminder: "green",
};

// Shared factory passed to each step's `chips(cfg, { chip, truncate, ALERT_COLORS })` (see
// index.js's buildStepDetailChips dispatcher). Returns a plain chip descriptor without a
// `key`; the dispatcher assigns keys once all of a step's chips are collected.
export function chip(label, icon, color, tooltip) {
  return { label, icon, color: color || undefined, tooltip };
}

export function humanize(type) {
  if (!type) return "";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function stepIcon(type) {
  return STEP_ICONS[type] || "mdi-circle-outline";
}

export function stepDotColor(type) {
  return STEP_DOT_COLORS[type] || "primary";
}

export function truncate(value, length) {
  if (!value) return "";
  const text = String(value);
  return text.length > length ? text.slice(0, length) + "..." : text;
}

export function buildTextPreview(step, maxLength = 120) {
  const cfg = step.config_json;
  if (!cfg || typeof cfg !== "object") return "";
  const type = step.step_type;

  if (type === "llm_call" && cfg.prompt) return truncate(cfg.prompt, maxLength);
  if (type === "condition" && cfg.expression)
    return truncate(cfg.expression, Math.min(maxLength, 100));
  if (type === "notification" && (cfg.message_template || cfg.telegram_template)) {
    return truncate(cfg.message_template || cfg.telegram_template, maxLength);
  }
  // These read the steps' real config keys; `query` and `content` never existed, so the
  // previews never rendered.
  if ((type === "semantic_memory_query" || type === "knowledge_query") && cfg.query_text)
    return truncate(cfg.query_text, Math.min(maxLength, 100));
  if (type === "semantic_memory_write" && cfg.description_key)
    return truncate(`from ${cfg.description_key}`, Math.min(maxLength, 100));
  return "";
}

// A step that writes its result under a configurable key (semantic_memory_query's
// output_key) declares its schema under the default key plus an `x-output-key` marker
// naming the config field. This returns the schema as this step instance actually
// writes it, so variable autocomplete offers the key the rule really produces.
export function instanceOutputSchema(schema, config) {
  const marker = schema?.["x-output-key"];
  const properties = schema?.properties;
  if (!marker || !properties || !(marker.default in properties)) return schema;
  const key = String(config?.[marker.config_field] ?? "").trim();
  if (!key || key === marker.default) return schema;
  const { [marker.default]: moved, ...rest } = properties;
  return { ...schema, properties: { ...rest, [key]: moved } };
}
