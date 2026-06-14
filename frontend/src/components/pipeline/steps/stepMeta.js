export const STEP_LABELS = {
  activity_detection: "Record Activity",
  activity_session_start: "Start Activity Session",
  activity_session_end: "End Activity Session",
  condition: "Condition",
  cts_window_poll: "CTS Window Poll",
  daily_report: "Daily Report",
  ha_action: "HA Action",
  home_state: "Home State",
  image_crop: "Crop Image",
  info_card: "Info Card",
  interactive_prompt: "Interactive Prompt",
  llm_call: "LLM Call",
  media_window_poll: "Media Window Poll",
  notification: "Notification",
  object_trend_analysis: "Room Trend Query",
  person_identification: "Person Identification",
  presence_query: "Presence Query",
  recamera_media_poll: "Recamera Media Poll",
  scene_analysis: "Scene Analysis",
  semantic_memory_query: "Memory Query",
  semantic_memory_write: "Memory Write",
  verification: "Verify Activity",
  wait: "Wait",
};

export const STEP_ICONS = {
  activity_detection: "mdi-run",
  activity_session_start: "mdi-play",
  activity_session_end: "mdi-stop",
  condition: "mdi-help-circle-outline",
  cts_window_poll: "mdi-camera-burst",
  daily_report: "mdi-file-chart",
  ha_action: "mdi-home-automation",
  home_state: "mdi-home-variant",
  image_crop: "mdi-crop",
  info_card: "mdi-card-text-outline",
  interactive_prompt: "mdi-message-question",
  llm_call: "mdi-brain",
  media_window_poll: "mdi-camera-burst",
  notification: "mdi-bell-outline",
  object_trend_analysis: "mdi-chart-line",
  person_identification: "mdi-face-recognition",
  presence_query: "mdi-map-marker-radius",
  recamera_media_poll: "mdi-camera-wireless-outline",
  scene_analysis: "mdi-image-search",
  semantic_memory_query: "mdi-database-search-outline",
  semantic_memory_write: "mdi-database-plus-outline",
  verification: "mdi-check-decagram-outline",
  wait: "mdi-timer-sand",
};

export const STEP_DOT_COLORS = {
  activity_detection: "indigo",
  activity_session_start: "green",
  activity_session_end: "red",
  condition: "blue-grey",
  cts_window_poll: "teal",
  daily_report: "indigo",
  ha_action: "blue",
  home_state: "blue",
  image_crop: "teal",
  info_card: "cyan",
  interactive_prompt: "cyan",
  llm_call: "purple",
  media_window_poll: "teal",
  notification: "orange",
  object_trend_analysis: "teal",
  person_identification: "indigo",
  presence_query: "blue",
  recamera_media_poll: "teal",
  scene_analysis: "teal",
  semantic_memory_query: "teal",
  semantic_memory_write: "indigo",
  verification: "green",
  wait: "amber",
};

const ALERT_COLORS = { emergency: "red", warning: "orange", info: "blue", reminder: "green" };

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

export function collectTemplateTokens(config) {
  if (!config || typeof config !== "object") return [];
  const strings = [];
  function collect(obj) {
    if (typeof obj === "string") {
      strings.push(obj);
      return;
    }
    if (obj && typeof obj === "object") Object.values(obj).forEach(collect);
  }
  collect(config);
  if (!strings.length) return [];
  const tokens = new Set();
  const re = /\{\{\s*([\w][\w.]*)\s*\}\}/g;
  for (const text of strings) {
    let match;
    while ((match = re.exec(text)) !== null) tokens.add(match[1]);
  }
  return Array.from(tokens);
}

export function buildStepDetailChips(step) {
  const cfg = step.config_json;
  if (!cfg || typeof cfg !== "object") return [];
  const type = step.step_type;
  const chips = [];
  let key = 0;
  const chip = (label, icon, color, tooltip) => {
    chips.push({ key: key++, label, icon, color: color || undefined, tooltip });
  };

  if (type === "llm_call") {
    if (cfg.model_id) {
      const short = truncate(cfg.model_id, 28);
      chip(short, "mdi-chip", "purple", cfg.model_id !== short ? cfg.model_id : undefined);
    }
    const maxImgs = cfg.max_images ?? 5;
    const triggerImgs = cfg.trigger_images_count ?? 0;
    const additionalSensors = cfg.additional_sensor_ids?.length || 0;
    const additionalRooms = cfg.additional_room_names?.length || 0;
    if (maxImgs > 0) chip(`<= ${maxImgs} images`, "mdi-image-multiple-outline", "teal");
    if (triggerImgs > 0) chip(`${triggerImgs} trigger frame${triggerImgs > 1 ? "s" : ""}`, "mdi-camera", "teal");
    if (additionalSensors > 0) chip(`+${additionalSensors} sensor${additionalSensors > 1 ? "s" : ""}`, "mdi-camera-plus-outline", "cyan");
    if (additionalRooms > 0) chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan");
    if (cfg.output_key && cfg.output_key !== "llm_response") chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
    if (cfg.response_format && cfg.response_format !== "default") chip(cfg.response_format, "mdi-code-json", "blue-grey");
  }

  if (type === "scene_analysis") {
    const source = cfg.image_source || "trigger";
    chip(source, "mdi-image-outline", "teal");
    const maxImgs = cfg.max_images ?? 1;
    if (maxImgs > 1) chip(`<= ${maxImgs} images`, "mdi-image-multiple-outline", "teal");
    if (cfg.run_detect !== false) chip("detect", "mdi-eye-outline", "green");
    if (cfg.run_describe !== false) chip("describe", "mdi-text-box-outline", "green");
    if (cfg.run_hazards !== false) chip("hazards", "mdi-alert-outline", "orange");
    if (cfg.run_embed) chip("embed", "mdi-vector-combine", "blue");
    const addSensors = cfg.additional_sensor_ids?.length || 0;
    const addRooms = cfg.additional_room_names?.length || 0;
    if (addSensors > 0) chip(`+${addSensors} sensor${addSensors > 1 ? "s" : ""}`, "mdi-camera-plus-outline", "cyan");
    if (addRooms > 0) chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan");
    if (cfg.output_key && cfg.output_key !== "scene_images") chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
  }

  if (type === "notification") {
    const level = cfg.alert_level || "warning";
    chip(level, "mdi-bell-outline", ALERT_COLORS[level] || "orange");
    if (cfg.channels?.length) chip(cfg.channels.join(", "), "mdi-send-outline", undefined);
    const telegramSrc = cfg.telegram_image_source;
    if (telegramSrc && telegramSrc !== "trigger") chip(`telegram: ${telegramSrc}`, "mdi-send", "blue");
    if (cfg.trigger_cooloff === false) chip("no cooloff", "mdi-timer-off-outline", "warning");
  }

  if (type === "condition" && cfg.trigger_cooloff) {
    chip("cooloff on match", "mdi-timer-outline", "blue-grey");
  }

  if (type === "person_identification") {
    if (cfg.target_persons?.length) {
      chip(cfg.target_persons.join(", "), "mdi-account-outline", "indigo");
    } else {
      chip("all persons", "mdi-account-group-outline", "indigo");
    }
    if (cfg.min_confidence != null) chip(`>= ${Math.round(cfg.min_confidence * 100)}% conf`, "mdi-percent", "teal");
    if (cfg.include_annotated_image) chip("annotated image", "mdi-image-edit-outline", undefined);
    if (cfg.write_movements_to_memory) chip("writes to memory", "mdi-database-arrow-up-outline", "purple");
  }

  if (type === "ha_action") {
    const domain = cfg.domain || "";
    const service = cfg.service || "";
    if (domain || service) chip(`${domain}.${service}`, "mdi-home-automation", "blue");
    if (cfg.entity_id) chip(truncate(cfg.entity_id, 32), "mdi-identifier", undefined, cfg.entity_id.length > 32 ? cfg.entity_id : undefined);
  }

  if (type === "wait") {
    const mins = cfg.minutes ?? 5;
    chip(`${mins} min`, "mdi-timer-sand", "amber");
  }

  if (type === "verification") {
    if (cfg.conditions?.length) {
      const mode = cfg.match_mode || "all";
      chip(`${cfg.conditions.length} condition${cfg.conditions.length > 1 ? "s" : ""} (${mode})`, "mdi-check-all", undefined);
    }
    if (cfg.re_notify_if_failed) chip(`re-notify ${cfg.re_notify_delay_minutes || 5}min`, "mdi-bell-ring-outline", "orange");
  }

  if (type === "activity_detection") {
    if (cfg.activity_type) chip(cfg.activity_type, "mdi-run", "indigo");
    if (cfg.person_id) chip(cfg.person_id, "mdi-account-outline", undefined);
    if (cfg.room_name) chip(cfg.room_name, "mdi-home-outline", undefined);
    const conf = cfg.confidence ?? 0.8;
    chip(`${Math.round(conf * 100)}% conf`, "mdi-percent", "teal");
  }

  if (type === "activity_session_start" || type === "activity_session_end") {
    if (cfg.activity_type) chip(cfg.activity_type, "mdi-run", "indigo");
    if (cfg.source_key) chip(`source: ${cfg.source_key}`, "mdi-link-variant", "blue-grey");
  }

  if (type === "object_trend_analysis") {
    if (cfg.room_ids?.length) chip(cfg.room_ids.join(", "), "mdi-home-group", "indigo");
    else chip("all rooms", "mdi-home-group", "indigo");
    if (cfg.severity_threshold) chip(cfg.severity_threshold, "mdi-alert-circle-outline", undefined);
    if (cfg.output_key && cfg.output_key !== "room_trends") chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
  }

  if (type === "semantic_memory_query") {
    if (cfg.output_key) chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey");
    if (cfg.top_k) chip(`top ${cfg.top_k}`, "mdi-format-list-numbered", undefined);
  }

  if (type === "semantic_memory_write" && cfg.source_key) {
    chip(`source: ${cfg.source_key}`, "mdi-link-variant", "blue-grey");
  }

  if (type === "image_crop") {
    const source = cfg.image_source || "trigger";
    chip(source, "mdi-image-outline", "teal");
    const regionCount = cfg.regions?.length || 0;
    if (regionCount > 0) chip(`${regionCount} region${regionCount > 1 ? "s" : ""}`, "mdi-crop", "green");
    const maxImgs = cfg.max_images ?? 1;
    if (maxImgs > 0) chip(`max ${maxImgs}`, "mdi-image-multiple-outline", "teal");
  }

  return chips;
}

export function buildTextPreview(step, maxLength = 120) {
  const cfg = step.config_json;
  if (!cfg || typeof cfg !== "object") return "";
  const type = step.step_type;

  if (type === "llm_call" && cfg.prompt) return truncate(cfg.prompt, maxLength);
  if (type === "condition" && cfg.expression) return truncate(cfg.expression, Math.min(maxLength, 100));
  if (type === "notification" && (cfg.message_template || cfg.telegram_template)) {
    return truncate(cfg.message_template || cfg.telegram_template, maxLength);
  }
  if (type === "semantic_memory_query" && cfg.query) return truncate(cfg.query, Math.min(maxLength, 100));
  if (type === "semantic_memory_write" && cfg.content) return truncate(cfg.content, Math.min(maxLength, 100));
  return "";
}
