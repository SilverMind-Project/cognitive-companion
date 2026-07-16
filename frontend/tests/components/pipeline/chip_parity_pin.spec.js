import { describe, expect, it } from "vitest";
import { buildStepDetailChips } from "@/components/pipeline/steps/index.js";

// Pins buildStepDetailChips' output, one representative config per step type that has a
// chip-producing block, BEFORE it is split into per-step chips(cfg, helpers) functions
// co-located in each step's *Config.vue (backend-hardening-m14 task 8). This spec must not
// change in the same commit as that refactor; a green, unmodified run here is the mechanical
// check that the move was behavior-preserving.

const FIXTURES = {
  llm_call: {
    model_id: "vllm-qwen3-32b-instruct-quantized-fp8",
    max_images: 3,
    trigger_images_count: 2,
    additional_sensor_ids: ["cam_kitchen", "cam_hall"],
    additional_room_names: ["Kitchen"],
    output_key: "custom_llm_out",
    response_format: "json",
  },
  scene_analysis: {
    image_source: "additional",
    max_images: 2,
    run_detect: false,
    run_describe: true,
    run_hazards: false,
    run_embed: true,
    additional_sensor_ids: ["cam_bath"],
    additional_room_names: ["Bathroom"],
    output_key: "custom_scene_out",
  },
  notification: {
    alert_level: "emergency",
    channels: ["telegram", "pwa_popup_text"],
    telegram_image_source: "additional",
    trigger_cooloff: false,
  },
  condition: {
    trigger_cooloff: true,
  },
  person_identification: {
    target_persons: ["grandma"],
    min_confidence: 0.85,
    include_annotated_image: true,
    write_movements_to_memory: true,
  },
  ha_action: {
    domain: "light",
    service: "turn_on",
    entity_id: "light.living_room_lamp_with_a_very_long_entity_id_string",
  },
  wait: {
    minutes: 15,
  },
  verification: {
    conditions: [{ expression: "true" }, { expression: "false" }],
    match_mode: "any",
    re_notify_if_failed: true,
    re_notify_delay_minutes: 10,
  },
  activity_detection: {
    activity_type: "eating",
    person_id: "grandma",
    room_name: "Kitchen",
    confidence: 0.9,
  },
  activity_session_start: {
    activity_type: "cooking",
    source_key: "stove_sensor",
  },
  activity_session_end: {
    activity_type: "cooking",
    source_key: "stove_sensor",
  },
  object_trend_analysis: {
    room_ids: ["kitchen", "bathroom"],
    severity_threshold: "high",
    output_key: "custom_trends_out",
  },
  semantic_memory_query: {
    output_key: "custom_mem_out",
    top_k: 5,
  },
  semantic_memory_write: {
    source_key: "observation_1",
  },
  image_crop: {
    image_source: "additional",
    regions: [{ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 }],
    max_images: 3,
  },
};

describe("buildStepDetailChips parity pin", () => {
  for (const [stepType, configJson] of Object.entries(FIXTURES)) {
    it(`pins chip output for '${stepType}'`, () => {
      const chips = buildStepDetailChips({ step_type: stepType, config_json: configJson });
      expect(chips).toMatchSnapshot();
    });
  }
});
