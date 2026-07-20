<!-- Backend: backend/steps/builtin/llm_call.py -->
<template>
  <!-- General tab -->
  <div v-if="tab === 'general'">
    <v-select
      :model-value="modelValue.model_id"
      :items="llmModelItems"
      :item-title="(m) => m.name || m.id"
      :item-value="(m) => m.id"
      label="Model"
      hint="Select a model from the registry (settings.yaml → llm.models)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, model_id: $event })"
    >
      <template #item="{ item, props: itemProps }">
        <v-list-item v-bind="itemProps">
          <template #append>
            <div class="d-flex ga-1 ml-2">
              <v-chip
                v-for="cap in item.raw.capabilities || []"
                :key="cap"
                size="x-small"
                :color="capabilityColor(cap)"
                variant="tonal"
                >{{ cap }}</v-chip
              >
            </div>
          </template>
        </v-list-item>
      </template>
    </v-select>

    <div v-if="selectedModel" class="d-flex ga-1 mb-4 flex-wrap">
      <v-chip
        v-for="cap in selectedModel.capabilities"
        :key="cap"
        size="small"
        :color="capabilityColor(cap)"
        variant="tonal"
        >{{ cap }}</v-chip
      >
      <v-chip size="small" variant="outlined">{{ selectedModel.api_type }}</v-chip>
      <v-chip v-if="selectedModel.guided_decoding" size="small" color="success" variant="tonal"
        >guided decoding</v-chip
      >
      <v-chip v-if="selectedModel.supports_thinking" size="small" color="secondary" variant="tonal"
        >thinking</v-chip
      >
    </div>

    <TemplateInput
      :model-value="modelValue.prompt"
      label="Prompt"
      multiline
      :rows="6"
      hint="Use {{variable}} for template values. Type {{ to trigger autocomplete."
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, prompt: $event })"
    />

    <TemplateInput
      :model-value="modelValue.special_instructions"
      label="Special Instructions (prepended to prompt)"
      multiline
      :rows="3"
      hint="Useful for style guides, translation instructions, etc. Supports {{ }} template syntax."
      class="mb-4"
      @update:model-value="
        emit('update:modelValue', { ...modelValue, special_instructions: $event })
      "
    />

    <v-combobox
      :model-value="modelValue.include_context"
      :items="contextKeys"
      label="Include Context Keys"
      multiple
      chips
      closable-chips
      hint="Pipeline data keys to include as context above the prompt."
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, include_context: $event })"
    />
  </div>

  <!-- Images tab -->
  <div v-else-if="tab === 'images'">
    <v-alert
      v-if="
        !(
          selectedModel &&
          selectedModel.capabilities &&
          selectedModel.capabilities.includes('vision')
        )
      "
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      Image inputs are silently skipped when the selected model does not have the vision capability.
    </v-alert>

    <ImageSourceSelector
      :model-value="modelValue"
      :sources="llmSources"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      show-max-images
      show-trigger-card
      show-time-filter
      max-images-hint="Hard cap on total images sent to the model"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <template #default="{ isAdditional }">
        <v-card v-if="isAdditional" variant="tonal" class="mb-4 pa-4">
          <v-checkbox
            :model-value="modelValue.sort_by_sensor_then_time"
            label="Group by sensor, then chronological within each sensor"
            hide-details
            @update:model-value="
              emit('update:modelValue', { ...modelValue, sort_by_sensor_then_time: $event })
            "
          />
          <div class="text-caption text-medium-emphasis ml-8 mt-1">
            Enables inter-frame temporal analysis. Images are ordered: all frames from sensor 1
            (oldest to newest), then sensor 2, etc.
          </div>
        </v-card>

        <v-checkbox
          :model-value="modelValue.use_annotated_image"
          label="Use annotated image (from person identification)"
          hide-details
          class="mb-4"
          @update:model-value="
            emit('update:modelValue', { ...modelValue, use_annotated_image: $event })
          "
        />
      </template>
    </ImageSourceSelector>
  </div>

  <!-- Output tab -->
  <div v-else-if="tab === 'output'">
    <v-select
      :model-value="modelValue.response_format"
      :items="[
        { title: 'Free text', value: 'text' },
        { title: 'JSON with schema (guided decoding)', value: 'json_schema' },
        { title: 'Free JSON (no schema)', value: 'json_free' },
      ]"
      item-title="title"
      item-value="value"
      label="Response Format"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, response_format: $event })"
    />
    <template
      v-if="
        modelValue.response_format === 'json_schema' || modelValue.response_format === 'json_free'
      "
    >
      <v-textarea
        :model-value="modelValue.response_schema"
        label="Format Instruction (appended to prompt)"
        rows="3"
        hint="Natural-language description of expected JSON keys, appended to the prompt"
        persistent-hint
        class="mb-4"
        @update:model-value="emit('update:modelValue', { ...modelValue, response_schema: $event })"
      />
    </template>
    <template v-if="modelValue.response_format === 'json_schema'">
      <v-textarea
        :model-value="modelValue.response_json_schema"
        label="JSON Schema"
        rows="10"
        :hint="
          selectedModel && selectedModel.guided_decoding
            ? 'Schema enforced via guided decoding (vLLM). Leave empty to rely on prompt instruction only.'
            : 'Schema injected as a prompt instruction (this model does not support guided decoding).'
        "
        persistent-hint
        :error-messages="llmJsonSchemaError"
        class="mb-4"
        @update:model-value="onJsonSchemaChange"
      />
    </template>
    <v-text-field
      :model-value="modelValue.output_key"
      label="Output Key"
      hint="Pipeline data key for the result. Use 'logic_response' or 'translation' for downstream step compatibility."
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
    />
  </div>

  <!-- Advanced tab -->
  <div v-else-if="tab === 'advanced'">
    <v-checkbox
      v-if="selectedModel && selectedModel.supports_thinking"
      :model-value="modelValue.thinking"
      label="Enable thinking (chain-of-thought)"
      hint="The model reasons inside &lt;think&gt;…&lt;/think&gt; tags. Only the final answer is stored."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, thinking: $event })"
    />

    <v-divider v-if="selectedModel" class="mb-4" />

    <div class="text-subtitle-2 mb-3">Sampling Overrides</div>
    <div class="text-caption text-medium-emphasis mb-4">
      Leave blank to use the model default
      <span v-if="selectedModel">
        (temperature: {{ selectedModel.default_temperature ?? "—" }}, top_p:
        {{ selectedModel.default_top_p ?? "—" }}, max_tokens:
        {{ selectedModel.default_max_tokens ?? "—" }}) </span
      >.
    </div>

    <v-row dense>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.temperature"
          label="Temperature"
          type="number"
          :min="0"
          :max="2"
          :step="0.05"
          clearable
          hint="0 - 2"
          persistent-hint
          @update:model-value="
            emit('update:modelValue', {
              ...modelValue,
              temperature: $event === '' ? null : Number($event),
            })
          "
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.top_p"
          label="Top-p"
          type="number"
          :min="0"
          :max="1"
          :step="0.05"
          clearable
          hint="0 - 1"
          persistent-hint
          @update:model-value="
            emit('update:modelValue', {
              ...modelValue,
              top_p: $event === '' ? null : Number($event),
            })
          "
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.max_tokens"
          label="Max Tokens"
          type="number"
          :min="1"
          clearable
          hint="tokens"
          persistent-hint
          @update:model-value="
            emit('update:modelValue', {
              ...modelValue,
              max_tokens: $event === '' ? null : Number($event),
            })
          "
        />
      </v-col>
    </v-row>

    <v-divider class="my-4" />

    <v-text-field
      :model-value="modelValue.hallucination_marker"
      label="Hallucination Marker"
      hint="If this string appears in the response, the call is automatically retried."
      persistent-hint
      @update:model-value="
        emit('update:modelValue', { ...modelValue, hallucination_marker: $event })
      "
    />
  </div>
</template>

<script>
import { ref, computed } from "vue";
import ImageSourceSelector, { DEFAULT_IMAGE_SOURCES } from "./_shared/ImageSourceSelector.vue";
import TemplateInput from "./_shared/TemplateInput.vue";

export const stepDefaults = {
  model_id: "",
  prompt: "",
  include_context: [],
  image_source: "none",
  max_images: 5,
  trigger_images_count: 0,
  additional_sensor_ids: [],
  additional_room_names: [],
  images_per_sensor: 3,
  sensor_frame_limits: {},
  sort_by_sensor_then_time: false,
  use_annotated_image: false,
  image_time_filter: {},
  pipeline_image_path: "",
  pipeline_image_url_field: "url",
  pipeline_image_object_name_field: "object_name",

  response_format: "text",
  response_schema: "",
  response_json_schema: "",
  output_key: "llm_response",
  special_instructions: "",
  hallucination_marker: "",
  thinking: false,
  temperature: null,
  top_p: null,
  max_tokens: null,
};

export const stepTabs = [
  { key: "images", label: "Images", icon: "mdi-camera-outline" },
  { key: "output", label: "Output", icon: "mdi-code-json" },
  { key: "advanced", label: "Advanced", icon: "mdi-tune" },
];

export function beforeSave(cfg) {
  // No special normalization needed — all fields are already in the right shape
  return cfg;
}

export function onStepLoaded(_cfg) {
  // Validate JSON schema field if present
  // Handled by the component internally
}

export function chips(cfg, { chip, truncate }) {
  const out = [];
  if (cfg.model_id) {
    const short = truncate(cfg.model_id, 28);
    out.push(chip(short, "mdi-chip", "purple", cfg.model_id !== short ? cfg.model_id : undefined));
  }
  const maxImgs = cfg.max_images ?? 5;
  const triggerImgs = cfg.trigger_images_count ?? 0;
  const additionalSensors = cfg.additional_sensor_ids?.length || 0;
  const additionalRooms = cfg.additional_room_names?.length || 0;
  if (maxImgs > 0) out.push(chip(`<= ${maxImgs} images`, "mdi-image-multiple-outline", "teal"));
  if (triggerImgs > 0)
    out.push(
      chip(`${triggerImgs} trigger frame${triggerImgs > 1 ? "s" : ""}`, "mdi-camera", "teal"),
    );
  if (additionalSensors > 0)
    out.push(
      chip(
        `+${additionalSensors} sensor${additionalSensors > 1 ? "s" : ""}`,
        "mdi-camera-plus-outline",
        "cyan",
      ),
    );
  if (additionalRooms > 0)
    out.push(chip(cfg.additional_room_names.join(", "), "mdi-home-outline", "cyan"));
  if (cfg.output_key && cfg.output_key !== "llm_response")
    out.push(chip(`-> ${cfg.output_key}`, "mdi-export-variant", "blue-grey"));
  if (cfg.response_format && cfg.response_format !== "default")
    out.push(chip(cfg.response_format, "mdi-code-json", "blue-grey"));
  return out;
}
</script>

<script setup>
const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  llmModelItems: { type: Array, default: () => [] },
  contextKeys: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);

// llm_call additionally supports text-only calls (no image source).
const llmSources = [{ title: "None (text only)", value: "none" }, ...DEFAULT_IMAGE_SOURCES];

const llmJsonSchemaError = ref("");

const selectedModel = computed(
  () => props.llmModelItems.find((m) => m.id === props.modelValue.model_id) || null,
);

function onJsonSchemaChange(val) {
  const updated = { ...props.modelValue, response_json_schema: val };
  if (val) {
    try {
      JSON.parse(val);
      llmJsonSchemaError.value = "";
    } catch (e) {
      llmJsonSchemaError.value = "Invalid JSON: " + e.message;
    }
  } else {
    llmJsonSchemaError.value = "";
  }
  emit("update:modelValue", updated);
}

function capabilityColor(cap) {
  return { text: "primary", vision: "indigo", translation: "teal" }[cap] || "grey";
}

defineExpose({ llmJsonSchemaError });
</script>
