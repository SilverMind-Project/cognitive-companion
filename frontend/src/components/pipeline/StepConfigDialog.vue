<template>
  <v-dialog
    :model-value="modelValue"
    width="1120"
    max-width="96vw"
    :fullscreen="$vuetify.display.smAndDown"
    scrollable
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card class="step-config-card d-flex flex-column">
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
              <!-- General tab (always present) -->
              <v-window-item value="general">
                <v-text-field
                  v-model="localStep.label"
                  label="Step Label"
                  hint="Optional display name for this step"
                  persistent-hint
                  class="mb-5"
                />

                <!-- person_identification -->
                <template v-if="localStep.step_type === 'person_identification'">
                  <v-combobox
                    v-model="cfg.target_persons"
                    :items="availablePersons"
                    label="Target Persons"
                    multiple
                    chips
                    closable-chips
                    hint="Select persons to identify, or leave empty for all"
                    persistent-hint
                    class="mb-4"
                  />
                  <v-slider
                    v-model="cfg.min_confidence"
                    label="Min Confidence"
                    :min="0" :max="1" :step="0.05"
                    thumb-label="always"
                    color="primary"
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.include_annotated_image" label="Include annotated image" class="mb-1" hide-details />
                  <v-checkbox v-model="cfg.include_motion" label="Include motion data" class="mb-1" hide-details />
                  <v-checkbox v-model="cfg.save_guest_images" label="Save guest images (unidentified faces)" class="mb-4" hide-details />
                  <v-combobox
                    v-model="cfg.additional_sensor_ids"
                    :items="[]"
                    label="Additional Sensor IDs"
                    multiple
                    chips
                    closable-chips
                    hint="Pull recent frames from these extra cameras in addition to the trigger sensor"
                    persistent-hint
                    class="mb-2"
                  />
                </template>

                <!-- ha_action -->
                <template v-if="localStep.step_type === 'ha_action'">
                  <v-row>
                    <v-col cols="6">
                      <v-text-field v-model="cfg.domain" label="Domain" placeholder="e.g. light, switch, script" />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field v-model="cfg.service" label="Service" placeholder="e.g. turn_on, toggle" />
                    </v-col>
                  </v-row>
                  <v-combobox
                    v-model="cfg.entity_id"
                    :items="haEntityItems"
                    :item-title="(item) => item.name ? `${item.name} (${item.entity_id})` : (item.entity_id || item)"
                    :item-value="(item) => item.entity_id || item"
                    label="Entity ID"
                    placeholder="e.g. light.living_room"
                    hint="Select from discovered entities or type an entity ID"
                    persistent-hint
                    class="mb-4"
                  />
                  <v-textarea
                    v-model="cfg.data"
                    label="Service Data (JSON)"
                    rows="4"
                    placeholder='{ "brightness": 255 }'
                  />
                </template>

                <!-- activity_detection -->
                <template v-if="localStep.step_type === 'activity_detection'">
                  <v-combobox
                    v-model="cfg.activity_type"
                    :items="activityTypes"
                    label="Activity Type"
                    hint="Activity to record. Supports {{template}} syntax (e.g. {{logic_response.activity_type}})."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.person_id"
                    :items="availablePersons"
                    label="Person ID (optional)"
                    clearable
                    hint="Person to attribute this activity to. Supports {{template}} syntax. Leave empty for unknown person."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.room_name"
                    :items="availableRooms"
                    label="Room (optional)"
                    clearable
                    hint="Room where the activity occurred. Defaults to trigger room when empty."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.confidence"
                    label="Confidence"
                    hint="Fixed value (0-1) or {{template}} syntax. Defaults to 0.8."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-divider class="mb-4" />
                  <div class="text-overline text-medium-emphasis mb-2">Scene Description Capture</div>
                  <v-checkbox
                    v-model="cfg.capture_scene_description"
                    label="Capture scene description into activity record"
                    hint="Saves the upstream vision model output (e.g. vision_response) into metadata_json.scene_description for full auditability."
                    persistent-hint
                    hide-details
                    class="mb-3"
                  />
                  <v-combobox
                    v-if="cfg.capture_scene_description"
                    v-model="cfg.scene_description_key"
                    :items="contextKeys"
                    label="Scene Description Source Key"
                    hint="pipeline_data key to read as the scene description (default: vision_response)."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-textarea
                    v-model="cfg.metadata_extra"
                    label="Extra Metadata (JSON, optional)"
                    rows="3"
                    hint='Optional JSON merged into metadata_json. Supports {{template}} syntax, e.g. {"reasoning": "{{logic_response.reasoning}}"}'
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.trigger_cooloff" label="Trigger cool-off upon execution" hide-details />
                </template>

                <!-- wait -->
                <template v-if="localStep.step_type === 'wait'">
                  <v-text-field
                    v-model.number="cfg.minutes"
                    label="Wait Duration (minutes)"
                    type="number"
                    :min="0"
                  />
                </template>

                <!-- condition -->
                <template v-if="localStep.step_type === 'condition'">
                  <v-text-field
                    v-model="cfg.expression"
                    label="Condition Expression"
                    hint="Expression evaluated at runtime to decide if the pipeline continues."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.trigger_cooloff" label="Trigger cool-off if condition is met" hide-details />
                </template>

                <!-- llm_call: model + prompt -->
                <template v-if="localStep.step_type === 'llm_call'">
                  <v-select
                    v-model="cfg.model_id"
                    :items="llmModelItems"
                    :item-title="(m) => m.name || m.id"
                    :item-value="(m) => m.id"
                    label="Model"
                    hint="Select a model from the registry (settings.yaml → llm.models)"
                    persistent-hint
                    class="mb-4"
                  >
                    <template #item="{ item, props }">
                      <v-list-item v-bind="props">
                        <template #append>
                          <div class="d-flex ga-1 ml-2">
                            <v-chip
                              v-for="cap in (item.raw.capabilities || [])"
                              :key="cap"
                              size="x-small"
                              :color="capabilityColor(cap)"
                              variant="tonal"
                            >{{ cap }}</v-chip>
                          </div>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>

                  <div v-if="selectedLLMModel" class="d-flex ga-1 mb-4 flex-wrap">
                    <v-chip
                      v-for="cap in selectedLLMModel.capabilities"
                      :key="cap"
                      size="small"
                      :color="capabilityColor(cap)"
                      variant="tonal"
                    >{{ cap }}</v-chip>
                    <v-chip size="small" variant="outlined">{{ selectedLLMModel.api_type }}</v-chip>
                    <v-chip v-if="selectedLLMModel.guided_decoding" size="small" color="success" variant="tonal">guided decoding</v-chip>
                    <v-chip v-if="selectedLLMModel.supports_thinking" size="small" color="purple" variant="tonal">thinking</v-chip>
                  </div>

                  <v-textarea
                    v-model="cfg.prompt"
                    label="Prompt"
                    rows="6"
                    class="mb-4"
                    hint="Use {{variable}} for template values. Drag a chip from the right or click to insert."
                    persistent-hint
                  />

                  <v-textarea
                    v-model="cfg.special_instructions"
                    label="Special Instructions (prepended to prompt)"
                    rows="3"
                    hint="Useful for style guides, translation instructions, etc."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-combobox
                    v-model="cfg.include_context"
                    :items="contextKeys"
                    label="Include Context Keys"
                    multiple
                    chips
                    closable-chips
                    hint="Pipeline data keys to include as context above the prompt."
                    persistent-hint
                  />
                </template>

                <!-- vision_analysis: prompt -->
                <template v-if="localStep.step_type === 'vision_analysis'">
                  <v-textarea
                    v-model="cfg.prompt"
                    label="Vision Prompt"
                    rows="6"
                    class="mb-4"
                    hint="Use {{variable}} for template values, e.g. {{person_detections.0.name}}, {{room_name}}"
                    persistent-hint
                  />
                  <v-checkbox v-model="cfg.use_annotated_image" label="Use annotated image" hide-details class="mb-2" />
                  <v-checkbox
                    v-model="cfg.thinking"
                    label="Enable thinking (chain-of-thought)"
                    hint="The model reasons inside &lt;think&gt;…&lt;/think&gt; tags. Only the final answer is stored."
                    persistent-hint
                    class="mb-2"
                  />
                </template>

                <!-- notification general -->
                <template v-if="localStep.step_type === 'notification'">
                  <v-select
                    v-model="cfg.alert_level"
                    :items="['emergency', 'warning', 'info', 'reminder']"
                    label="Alert Level"
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.channels"
                    :items="availableChannels"
                    label="Notification Channels"
                    multiple
                    chips
                    closable-chips
                    hint="Select channels or type custom channel names. Leave empty to use defaults from notifications.yaml."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.trigger_cooloff" label="Trigger cool-off upon execution" hide-details />
                </template>

                <!-- verification: settings -->
                <template v-if="localStep.step_type === 'verification'">
                  <v-select
                    v-model="cfg.match_mode"
                    :items="['all', 'any']"
                    label="Match Mode"
                    hint="'all' = every condition must pass, 'any' = at least one"
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.re_notify_if_failed" label="Re-notify if verification fails" hide-details class="mb-3" />
                  <v-text-field
                    v-model.number="cfg.re_notify_delay_minutes"
                    label="Re-notify Delay (minutes)"
                    type="number"
                    :min="0"
                  />
                </template>

                <!-- Generic plugin step -->
                <template v-if="!knownTypes.includes(localStep.step_type) && localStep.step_type">
                  <v-alert type="info" variant="tonal" class="mb-4">
                    This step type uses a plugin configuration. Edit the JSON config below.
                  </v-alert>
                  <v-textarea
                    v-model="genericConfigJson"
                    label="Config JSON"
                    rows="12"
                    :error-messages="genericConfigError"
                  />
                </template>
              </v-window-item>

              <!-- Images tab (vision_analysis + llm_call) -->
              <v-window-item value="images">
                <template v-if="localStep.step_type === 'llm_call'">
                  <v-alert
                    v-if="!(selectedLLMModel && selectedLLMModel.capabilities && selectedLLMModel.capabilities.includes('vision'))"
                    type="info"
                    variant="tonal"
                    density="compact"
                    class="mb-4"
                  >
                    Image inputs are silently skipped when the selected model does not have the vision capability.
                  </v-alert>

                  <v-select
                    v-model="cfg.image_source"
                    :items="[
                      { title: 'None (text only)', value: 'none' },
                      { title: 'Trigger frames', value: 'trigger' },
                      { title: 'Additional cameras', value: 'additional' },
                      { title: 'Both (trigger + additional)', value: 'both' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="Image Source"
                    class="mb-4"
                  />

                  <v-text-field
                    v-if="cfg.image_source !== 'none'"
                    v-model.number="cfg.max_images"
                    label="Max Images (total)"
                    type="number"
                    :min="1"
                    hint="Hard cap on total images sent to the model"
                    persistent-hint
                    class="mb-4"
                  />

                  <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
                    <v-combobox
                      v-model="cfg.additional_sensor_ids"
                      :items="cameraSensorItems"
                      label="Camera Sensors (in analysis order)"
                      multiple
                      chips
                      closable-chips
                      hint="Sensors are processed in the order listed. Determines grouping when 'Sort by sensor' is on."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.additional_room_names"
                      :items="availableRooms"
                      label="Additional Rooms"
                      multiple
                      chips
                      closable-chips
                      hint="Pull images from all cameras in these rooms (unordered)"
                      persistent-hint
                      class="mb-4"
                    />

                    <v-card variant="tonal" class="mb-4 pa-4">
                      <v-checkbox
                        v-model="cfg.sort_by_sensor_then_time"
                        label="Group by sensor, then chronological within each sensor"
                        hide-details
                      />
                      <div class="text-caption text-medium-emphasis ml-8 mt-2">
                        Enables inter-frame temporal analysis. Images are ordered:
                        all frames from sensor 1 (oldest to newest), then sensor 2, etc.
                      </div>
                      <v-text-field
                        v-if="cfg.sort_by_sensor_then_time"
                        v-model.number="cfg.images_per_sensor"
                        label="Images per sensor"
                        density="compact"
                        type="number"
                        :min="1"
                        class="mt-3"
                      />
                    </v-card>

                    <v-card variant="outlined" class="pa-4">
                      <div class="text-subtitle-2 mb-3">
                        <v-icon size="small" class="mr-1">mdi-clock-outline</v-icon>
                        Time Filter (optional)
                      </div>
                      <v-text-field
                        v-model.number="llmImageTimeFilter.since_minutes"
                        label="Since (minutes ago)"
                        type="number"
                        :min="0"
                        class="mb-3"
                      />
                      <v-row>
                        <v-col cols="6">
                          <v-text-field v-model="llmImageTimeFilter.time_start" label="Time Start" placeholder="08:00" />
                        </v-col>
                        <v-col cols="6">
                          <v-text-field v-model="llmImageTimeFilter.time_end" label="Time End" placeholder="18:00" />
                        </v-col>
                      </v-row>
                    </v-card>
                  </template>
                </template>

                <template v-if="localStep.step_type === 'vision_analysis'">
                  <v-select
                    v-model="cfg.image_source"
                    :items="['trigger', 'additional', 'both']"
                    label="Image Source"
                    hint="trigger = frames that triggered the pipeline, additional = extra cameras, both = combine"
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model.number="cfg.max_images"
                    label="Max Images"
                    type="number"
                    :min="1"
                    hint="Maximum total images sent to the vision model"
                    persistent-hint
                    class="mb-4"
                  />
                  <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
                    <v-combobox
                      v-model="cfg.additional_sensor_ids"
                      :items="cameraSensorItems"
                      label="Additional Camera Sensors"
                      multiple
                      chips
                      closable-chips
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.additional_room_names"
                      :items="availableRooms"
                      label="Additional Rooms"
                      multiple
                      chips
                      closable-chips
                      class="mb-4"
                    />
                    <v-card variant="outlined" class="pa-4">
                      <div class="text-subtitle-2 mb-3">
                        <v-icon size="small" class="mr-1">mdi-clock-outline</v-icon>
                        Time Filter (optional)
                      </div>
                      <v-text-field
                        v-model.number="imageTimeFilter.since_minutes"
                        label="Since (minutes ago)"
                        type="number"
                        :min="0"
                        class="mb-3"
                      />
                      <v-row>
                        <v-col cols="6">
                          <v-text-field v-model="imageTimeFilter.time_start" label="Time Start" placeholder="08:00" />
                        </v-col>
                        <v-col cols="6">
                          <v-text-field v-model="imageTimeFilter.time_end" label="Time End" placeholder="18:00" />
                        </v-col>
                      </v-row>
                    </v-card>
                  </template>
                </template>
              </v-window-item>

              <!-- Output tab -->
              <v-window-item value="output">
                <template v-if="localStep.step_type === 'llm_call'">
                  <v-select
                    v-model="cfg.response_format"
                    :items="[
                      { title: 'Free text', value: 'text' },
                      { title: 'JSON with schema (guided decoding)', value: 'json_schema' },
                      { title: 'Free JSON (no schema)', value: 'json_free' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="Response Format"
                    class="mb-4"
                  />
                  <template v-if="cfg.response_format === 'json_schema' || cfg.response_format === 'json_free'">
                    <v-textarea
                      v-model="cfg.response_schema"
                      label="Format Instruction (appended to prompt)"
                      rows="3"
                      hint="Natural-language description of expected JSON keys, appended to the prompt"
                      persistent-hint
                      class="mb-4"
                    />
                  </template>
                  <template v-if="cfg.response_format === 'json_schema'">
                    <v-textarea
                      v-model="cfg.response_json_schema"
                      label="JSON Schema"
                      rows="10"
                      :hint="selectedLLMModel && selectedLLMModel.guided_decoding
                        ? 'Schema enforced via guided decoding (vLLM). Leave empty to rely on prompt instruction only.'
                        : 'Schema injected as a prompt instruction (this model does not support guided decoding).'"
                      persistent-hint
                      :error-messages="llmJsonSchemaError"
                      class="mb-4"
                    />
                  </template>
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="Pipeline data key for the result. Use 'logic_response', 'vision_response', or 'translation' for downstream step compatibility."
                    persistent-hint
                  />
                </template>

                <template v-if="localStep.step_type === 'vision_analysis'">
                  <v-select
                    v-model="cfg.response_format"
                    :items="['default', 'custom']"
                    label="Response Format"
                    hint="Controls the structured JSON output enforced on the vision model"
                    persistent-hint
                    class="mb-4"
                  />
                  <v-alert v-if="cfg.response_format === 'default'" type="info" variant="tonal" density="compact" class="mb-4">
                    <div class="text-subtitle-2 mb-1">Output keys (available as <code>vision_response</code>):</div>
                    String (default free-text output)
                  </v-alert>
                  <template v-if="cfg.response_format === 'custom'">
                    <v-textarea
                      v-model="cfg.response_schema"
                      label="Response Format Instruction"
                      rows="3"
                      hint="Text instruction appended to the prompt describing expected JSON keys"
                      persistent-hint
                      class="mb-4"
                    />
                    <v-textarea
                      v-model="cfg.response_json_schema"
                      label="JSON Schema (optional)"
                      rows="10"
                      hint="Paste a JSON Schema to enforce structured output via guided decoding."
                      persistent-hint
                      :error-messages="jsonSchemaError"
                    />
                  </template>
                </template>

              </v-window-item>

              <!-- Notification: templates tab -->
              <v-window-item value="templates">
                <template v-if="localStep.step_type === 'notification'">
                  <v-textarea
                    v-model="cfg.message_template"
                    label="Default Message Template"
                    rows="3"
                    hint="Default for all channels. Use {message}, {room}, {vision_response}, etc."
                    persistent-hint
                    class="mb-5"
                  />
                  <div class="text-overline text-medium-emphasis mb-2">Per-Channel Overrides</div>
                  <v-textarea
                    v-model="cfg.telegram_template"
                    label="Telegram Template"
                    rows="3"
                    hint="HTML supported. Falls back to the default template."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.eink_template"
                    label="E-Ink Template"
                    rows="2"
                    hint="Short plain-text for e-ink displays."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.ha_speaker_tts_template"
                    label="HA Speaker TTS / PWA Announcement Template"
                    rows="2"
                    hint="Natural language for spoken announcements (smart speakers and PWA TTS). Falls back to the default template."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.pwa_popup_text_template"
                    label="PWA Popup Text Template"
                    rows="2"
                    hint="Notification text shown in the companion UI overlay."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.pwa_realtime_ai_template"
                    label="PWA Realtime AI Template"
                    rows="2"
                    hint="Conversational voice prompt for Gemini Live delivery."
                    persistent-hint
                  />
                </template>
              </v-window-item>

              <!-- Notification: per-channel options -->
              <v-window-item value="channels">
                <template v-if="localStep.step_type === 'notification'">
                  <div v-if="cfg.channels && cfg.channels.includes('telegram')">
                    <div class="text-overline text-medium-emphasis mb-2">Telegram</div>
                    <v-select
                      v-model="cfg.telegram_image_source"
                      :items="[
                        { title: 'Trigger frame (default)', value: 'trigger' },
                        { title: 'None (text only)', value: 'none' },
                        { title: 'Additional cameras', value: 'additional' },
                        { title: 'Both (trigger + additional)', value: 'both' },
                      ]"
                      item-title="title"
                      item-value="value"
                      label="Image Source"
                      hint="Which image to attach to the Telegram message."
                      persistent-hint
                      class="mb-4"
                    />
                    <template v-if="cfg.telegram_image_source === 'additional' || cfg.telegram_image_source === 'both'">
                      <v-combobox
                        v-model="cfg.telegram_additional_sensor_ids"
                        :items="cameraSensorItems"
                        label="Camera Sensors (in order)"
                        multiple
                        chips
                        closable-chips
                        hint="Pull images from these camera sensors."
                        persistent-hint
                        class="mb-4"
                      />
                      <v-combobox
                        v-model="cfg.telegram_additional_room_names"
                        :items="availableRooms"
                        label="Additional Rooms"
                        multiple
                        chips
                        closable-chips
                        hint="Pull images from all cameras in these rooms."
                        persistent-hint
                        class="mb-4"
                      />
                      <v-card variant="tonal" class="mb-4 pa-4">
                        <v-checkbox
                          v-model="cfg.telegram_sort_by_sensor_then_time"
                          label="Group by sensor, then chronological within each sensor"
                          hide-details
                        />
                        <div class="text-caption text-medium-emphasis ml-8 mt-2">
                          Enables inter-frame temporal analysis per camera.
                        </div>
                        <v-text-field
                          v-if="cfg.telegram_sort_by_sensor_then_time"
                          v-model.number="cfg.telegram_images_per_sensor"
                          label="Images per sensor"
                          density="compact"
                          type="number"
                          :min="1"
                          class="mt-3"
                        />
                      </v-card>
                      <v-card variant="outlined" class="pa-4 mb-4">
                        <div class="text-subtitle-2 mb-3">
                          <v-icon size="small" class="mr-1">mdi-clock-outline</v-icon>
                          Time Filter (optional)
                        </div>
                        <v-text-field
                          v-model.number="notificationImageTimeFilter.since_minutes"
                          label="Since (minutes ago)"
                          type="number"
                          :min="0"
                          class="mb-3"
                        />
                        <v-row>
                          <v-col cols="6">
                            <v-text-field v-model="notificationImageTimeFilter.time_start" label="Time Start" placeholder="08:00" />
                          </v-col>
                          <v-col cols="6">
                            <v-text-field v-model="notificationImageTimeFilter.time_end" label="Time End" placeholder="18:00" />
                          </v-col>
                        </v-row>
                      </v-card>
                    </template>
                    <v-divider class="mb-4" />
                  </div>

                  <div v-if="cfg.channels && cfg.channels.includes('eink')">
                    <div class="text-overline text-medium-emphasis mb-2">E-Ink Display</div>
                    <v-combobox
                      v-model="cfg.eink_targets"
                      :items="einkSensorItems"
                      label="E-Ink Target Devices"
                      multiple
                      chips
                      closable-chips
                      hint="Select e-ink displays. Leave empty to dispatch to all e-ink devices."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-select
                      v-model="cfg.eink_template_id"
                      :items="imageTemplateItems"
                      :item-title="(item) => item.name || `Template #${item.id}`"
                      :item-value="(item) => item.id"
                      label="Image Template"
                      clearable
                      hint="Select an image template for the notification. Leave empty to use the default alert template."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-text-field
                      v-model.number="cfg.eink_expiry_minutes"
                      label="Expiry Duration (minutes)"
                      type="number"
                      :min="1"
                      hint="Number of minutes before the display reverts to the default template. Default: 30."
                      persistent-hint
                      class="mb-5"
                    />
                  </div>

                  <div v-if="cfg.channels && cfg.channels.includes('ha_speaker_tts')">
                    <div class="text-overline text-medium-emphasis mb-2">HA Speaker TTS</div>
                    <v-autocomplete
                      v-model="cfg.ha_media_player"
                      :items="haMediaPlayerItems"
                      :item-title="(item) => item.name || item.entity_id || item"
                      :item-value="(item) => item.entity_id || item"
                      label="TTS Media Player"
                      clearable
                      hint="Home Assistant media_player entity for TTS audio playback"
                      persistent-hint
                      class="mb-3"
                    />
                    <v-text-field
                      v-model="cfg.tts_language"
                      label="TTS Language"
                      clearable
                      placeholder="e.g. ta, en"
                      hint="Language code for TTS synthesis. Leave blank to use the server default."
                      persistent-hint
                      class="mb-3"
                    />
                    <v-select
                      v-model="cfg.tts_style"
                      :items="['', 'neutral', 'clear', 'formal', 'chat', 'happy', 'surprise', 'sad', 'fear', 'anger', 'disgust', 'narrative', 'enthusiastic', 'laugh', 'yawn', 'angry']"
                      label="TTS Style"
                      clearable
                      hint="Svara speaking style. Leave blank to use the server default."
                      persistent-hint
                    />
                  </div>

                  <div v-if="cfg.channels && cfg.channels.includes('webhook')" class="mt-5">
                    <div class="text-overline text-medium-emphasis mb-2">Webhook</div>
                    <v-text-field
                      v-model="cfg.webhook_url"
                      label="Webhook URL (optional)"
                      clearable
                      hint="Override global webhook endpoint (from settings/env)"
                      persistent-hint
                      class="mb-3"
                    />
                    <v-textarea
                      v-model="cfg.webhook_template"
                      label="Webhook JSON Template (optional)"
                      rows="5"
                      hint="JSON payload template. Uses {message}, {room}, etc. Falls back to a basic JSON envelope."
                      persistent-hint
                    />
                  </div>

                  <v-alert v-if="(!cfg.channels || (!cfg.channels.includes('telegram') && !cfg.channels.includes('ha_speaker_tts') && !cfg.channels.includes('webhook') && !cfg.channels.includes('eink')))" type="info" variant="tonal" density="compact" class="mt-3">
                    Add <code>telegram</code>, <code>ha_speaker_tts</code>, <code>eink</code>, or <code>webhook</code> on the General tab to configure their per-channel options here.
                  </v-alert>
                </template>
              </v-window-item>

              <!-- verification: conditions -->
              <v-window-item value="conditions">
                <template v-if="localStep.step_type === 'verification'">
                  <div class="d-flex align-center mb-3">
                    <div class="text-subtitle-2">Activity Conditions</div>
                    <v-spacer />
                    <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" @click="addCondition">Add Condition</v-btn>
                  </div>
                  <div v-if="!cfg.conditions || !cfg.conditions.length" class="text-center text-medium-emphasis py-4">
                    No conditions yet.
                  </div>
                  <v-card v-for="(cond, idx) in cfg.conditions" :key="idx" variant="outlined" class="mb-3 pa-4">
                    <div class="d-flex align-center mb-3">
                      <span class="text-caption font-weight-bold">Condition {{ idx + 1 }}</span>
                      <v-spacer />
                      <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="cfg.conditions.splice(idx, 1)" />
                    </div>
                    <v-row>
                      <v-col cols="12" md="6">
                        <v-combobox
                          v-model="cond.person_id"
                          :items="availablePersons"
                          label="Person ID (optional)"
                          density="compact"
                          clearable
                          hint="Leave empty to match any person."
                          persistent-hint
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-combobox
                          v-model="cond.activity_type"
                          :items="activityTypes"
                          label="Activity Type"
                          density="compact"
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-combobox
                          v-model="cond.room_name"
                          :items="availableRooms"
                          label="Room (optional)"
                          density="compact"
                          clearable
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-select
                          v-model="cond._time_mode"
                          :items="['relative', 'fixed']"
                          label="Time Window"
                          density="compact"
                        />
                      </v-col>
                      <v-col v-if="cond._time_mode !== 'fixed'" cols="12">
                        <v-text-field
                          v-model.number="cond.within_minutes"
                          label="Within Minutes"
                          density="compact"
                          type="number"
                          :min="0"
                        />
                      </v-col>
                      <template v-if="cond._time_mode === 'fixed'">
                        <v-col cols="6">
                          <v-text-field v-model="cond._window_start_time" label="Start Time (today)" density="compact" type="time" />
                        </v-col>
                        <v-col cols="6">
                          <v-text-field v-model="cond._window_end_time" label="End Time (today)" density="compact" type="time" />
                        </v-col>
                      </template>
                    </v-row>
                    <v-checkbox v-model="cond.completed" label="Expect completed (uncheck to verify NOT done)" density="compact" hide-details class="mt-2" />
                    <v-slider
                      v-model="cond.min_confidence"
                      label="Min Confidence"
                      :min="0" :max="1" :step="0.05"
                      thumb-label="always"
                      color="primary"
                      class="mt-2"
                    />
                  </v-card>
                </template>
              </v-window-item>

              <!-- Advanced tab (llm_call + vision_analysis sampling) -->
              <v-window-item value="advanced">

                <!-- vision_analysis sampling overrides -->
                <template v-if="localStep.step_type === 'vision_analysis'">
                  <div class="text-subtitle-2 mb-3">Sampling Overrides</div>
                  <div class="text-caption text-medium-emphasis mb-4">
                    Leave blank to use the model default.
                  </div>
                  <v-row dense>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.temperature"
                        label="Temperature"
                        type="number"
                        :min="0"
                        :max="2"
                        :step="0.05"
                        clearable
                        hint="0 - 2"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.top_p"
                        label="Top-p"
                        type="number"
                        :min="0"
                        :max="1"
                        :step="0.05"
                        clearable
                        hint="0 - 1"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.max_tokens"
                        label="Max Tokens"
                        type="number"
                        :min="1"
                        clearable
                        hint="tokens"
                        persistent-hint
                      />
                    </v-col>
                  </v-row>
                </template>

                <template v-if="localStep.step_type === 'llm_call'">
                  <!-- Thinking -->
                  <v-checkbox
                    v-if="selectedLLMModel && selectedLLMModel.supports_thinking"
                    v-model="cfg.thinking"
                    label="Enable thinking (chain-of-thought)"
                    hint="The model reasons inside &lt;think&gt;…&lt;/think&gt; tags. Only the final answer is stored."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-divider v-if="selectedLLMModel" class="mb-4" />

                  <!-- Sampling overrides -->
                  <div class="text-subtitle-2 mb-3">Sampling Overrides</div>
                  <div class="text-caption text-medium-emphasis mb-4">
                    Leave blank to use the model default
                    <span v-if="selectedLLMModel">
                      (temperature: {{ selectedLLMModel.default_temperature ?? '—' }},
                      top_p: {{ selectedLLMModel.default_top_p ?? '—' }},
                      max_tokens: {{ selectedLLMModel.default_max_tokens ?? '—' }})
                    </span>.
                  </div>

                  <v-row dense>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.temperature"
                        label="Temperature"
                        type="number"
                        :min="0"
                        :max="2"
                        :step="0.05"
                        clearable
                        hint="0 - 2"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.top_p"
                        label="Top-p"
                        type="number"
                        :min="0"
                        :max="1"
                        :step="0.05"
                        clearable
                        hint="0 - 1"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model.number="cfg.max_tokens"
                        label="Max Tokens"
                        type="number"
                        :min="1"
                        clearable
                        hint="tokens"
                        persistent-hint
                      />
                    </v-col>
                  </v-row>

                  <v-divider class="my-4" />

                  <v-text-field
                    v-model="cfg.hallucination_marker"
                    label="Hallucination Marker"
                    hint="If this string appears in the response, the call is automatically retried."
                    persistent-hint
                  />
                </template>
              </v-window-item>
            </v-window>
          </div>

          <!-- Pipeline Variables sidebar -->
          <v-divider vertical />
          <div class="step-config-vars px-4 py-5 d-none d-md-flex flex-column">
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
            <v-alert
              v-if="copiedToken"
              type="success"
              density="compact"
              variant="tonal"
              class="mt-2"
            >
              Copied {{ copiedToken }}
            </v-alert>
          </div>
        </div>
      </div>

      <v-divider />

      <v-card-actions class="px-6 py-3">
        <v-icon size="small" color="medium-emphasis" class="mr-1">mdi-information-outline</v-icon>
        <span class="text-caption text-medium-emphasis">
          Templates use <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts; notification templates use single-brace <code class="cc-code">{key}</code>.
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

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  step: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue", "save"]);

const knownTypes = [
  "llm_call",
  "person_identification", "vision_analysis",
  "notification", "ha_action", "activity_detection",
  "wait", "condition", "verification",
];

const STEP_ICONS = {
  person_identification: "mdi-face-recognition",
  llm_call: "mdi-brain",
  vision_analysis: "mdi-eye-outline",
  notification: "mdi-bell-outline",
  ha_action: "mdi-home-automation",
  activity_detection: "mdi-run",
  wait: "mdi-timer-sand",
  condition: "mdi-help-circle-outline",
  verification: "mdi-check-decagram-outline",
};

const stepIcon = computed(() => STEP_ICONS[localStep.step_type] || "mdi-cog-outline");

const contextKeys = [
  "vision_response",
  "person_detections",
  "logic_response",
  "translation",
  "detected_activities",
  "annotated_image",
  "verification",
  "condition",
];

const localStep = reactive({
  step_type: "",
  label: "",
});

const cfg = reactive({});
const genericConfigJson = ref("{}");
const genericConfigError = ref("");
const jsonSchemaError = ref("");
const imageTimeFilter = reactive({ since_minutes: null, time_start: "", time_end: "" });
const llmImageTimeFilter = reactive({ since_minutes: null, time_start: "", time_end: "" });
const notificationImageTimeFilter = reactive({ since_minutes: null, time_start: "", time_end: "" });
const llmJsonSchemaError = ref("");
const cameraSensorItems = ref([]);

const activeTab = ref("general");
const varSearch = ref("");
const copiedToken = ref("");

// LLM model registry (for the llm_call step)
const llmModelItems = ref([]);
const selectedLLMModel = computed(() =>
  llmModelItems.value.find((m) => m.id === cfg.model_id) || null
);

// Pipeline data reference for the always-visible sidebar.
const pipelineDataReference = [
  // -- Trigger context -------------------------------------------------------
  { key: "trigger.sensor_id", source: "Trigger context" },
  { key: "trigger.room_name", source: "Trigger context" },
  { key: "trigger.media_paths", source: "Trigger context" },
  { key: "room_name", source: "Trigger context (top-level alias)" },
  { key: "sensor_id", source: "Trigger context (top-level alias)" },
  { key: "trigger_input", source: "Webhook / Telegram trigger payload" },
  { key: "trigger_input.command", source: "Telegram trigger" },
  { key: "trigger_input.chat_id", source: "Telegram trigger" },
  { key: "trigger_input.args", source: "Telegram trigger (list)" },
  { key: "trigger_input.text", source: "Telegram / webhook raw text" },
  // -- Executor system context -----------------------------------------------
  { key: "system.local_time", source: "Executor system context" },
  { key: "system.local_date", source: "Executor system context" },
  { key: "system.local_day_of_week", source: "Executor system context" },
  { key: "system.timezone", source: "Executor system context" },
  // -- person_identification --------------------------------------------------
  { key: "person_detections", source: "person_identification" },
  { key: "person_detections.0.person_id", source: "person_identification (first match)" },
  { key: "person_detections.0.name", source: "person_identification (first match)" },
  { key: "person_detections.0.confidence", source: "person_identification (first match)" },
  { key: "person_detections.0.bbox", source: "person_identification — [x1,y1,x2,y2] in pixels" },
  { key: "person_detections.0.direction", source: "person_identification — motion direction" },
  { key: "person_detections.0.frame_index", source: "person_identification — index into trigger media_paths" },
  { key: "person_detections.0.source_media_path", source: "person_identification — presigned URL of the frame containing this bbox" },
  { key: "annotated_image", source: "person_identification — base64 image with bbox overlays" },
  // -- vision_analysis / llm_call (vision) ------------------------------------
  { key: "vision_response", source: "vision_analysis / llm_call" },
  // -- llm_call (reasoning) --------------------------------------------------
  { key: "logic_response", source: "llm_call (output_key=logic_response)" },
  { key: "logic_response.is_notification_needed", source: "llm_call (default notification schema)" },
  { key: "logic_response.user_notification", source: "llm_call (default notification schema)" },
  { key: "logic_response.alert_level", source: "llm_call (default notification schema)" },
  { key: "logic_response.reasoning", source: "llm_call (default notification schema)" },
  { key: "logic_response.activities", source: "llm_call (activity detection schema)" },
  // -- llm_call (custom output_key) ------------------------------------------
  { key: "llm_response", source: "llm_call (default output key)" },
  // -- llm_call (translation output) -----------------------------------------
  { key: "translation", source: "llm_call (output_key=translation)" },
  // -- activity_detection ----------------------------------------------------
  { key: "detected_activities", source: "activity_detection" },
  { key: "detected_activities.0.person_id", source: "activity_detection (first entry)" },
  { key: "detected_activities.0.activity_type", source: "activity_detection (first entry)" },
  { key: "detected_activities.0.confidence", source: "activity_detection (first entry)" },
  // -- verification ----------------------------------------------------------
  { key: "verification.verified", source: "verification" },
  { key: "verification.match_mode", source: "verification" },
  { key: "verification.matched_conditions", source: "verification" },
  { key: "verification.unmatched_conditions", source: "verification" },
  // -- condition -------------------------------------------------------------
  { key: "condition.result", source: "condition" },
  { key: "condition.expression", source: "condition" },
  { key: "condition.branch", source: "condition (true/false)" },
  // -- ha_action -------------------------------------------------------------
  { key: "ha_action.success", source: "ha_action" },
  { key: "ha_action.domain", source: "ha_action" },
  { key: "ha_action.service", source: "ha_action" },
  { key: "ha_action.entity_id", source: "ha_action" },
  // -- notification ----------------------------------------------------------
  { key: "notification_dispatched", source: "notification" },
  { key: "notification_channels", source: "notification" },
];

const filteredVariables = computed(() => {
  const q = varSearch.value.trim().toLowerCase();
  if (!q) return pipelineDataReference;
  return pipelineDataReference.filter(
    (v) => v.key.toLowerCase().includes(q) || v.source.toLowerCase().includes(q)
  );
});

// Tabs change based on step type, but always include "general".
const tabs = computed(() => {
  const all = [{ key: "general", label: "General", icon: "mdi-tune-variant" }];
  const t = localStep.step_type;
  if (t === "llm_call") {
    all.push({ key: "images", label: "Images", icon: "mdi-camera-outline" });
    all.push({ key: "output", label: "Output", icon: "mdi-code-json" });
    all.push({ key: "advanced", label: "Advanced", icon: "mdi-tune" });
  } else if (t === "vision_analysis") {
    all.push({ key: "images", label: "Images", icon: "mdi-camera-outline" });
    all.push({ key: "output", label: "Output", icon: "mdi-code-json" });
    all.push({ key: "advanced", label: "Advanced", icon: "mdi-tune" });
  } else if (t === "notification") {
    all.push({ key: "templates", label: "Templates", icon: "mdi-message-text-outline" });
    all.push({ key: "channels", label: "Channel Options", icon: "mdi-tune" });
  } else if (t === "verification") {
    all.unshift({ key: "conditions", label: "Conditions", icon: "mdi-check-decagram-outline" });
  }
  return all;
});

// Reset to first tab when step type changes.
watch(
  () => localStep.step_type,
  () => {
    if (tabs.value.length) activeTab.value = tabs.value[0].key;
  }
);

// Dynamic lists from API
const availableChannels = ref(["pwa_popup_text", "telegram", "eink", "ha_speaker_tts", "pwa_tts_announcement", "pwa_realtime_ai", "webhook"]);
const availablePersons = ref([]);
const availableRooms = ref([]);
const availableSensors = ref([]);
const einkSensorItems = ref([]);
const haMediaPlayerItems = ref([]);
const haEntityItems = ref([]);
const imageTemplateItems = ref([]);
const activityTypes = [
  // Daily living
  "eating", "drinking", "cooking", "meal_prep",
  // Rest and personal care
  "sleeping", "resting", "bathing", "grooming", "toileting", "dressing",
  // Medication and health
  "medication", "medication_morning", "medication_evening",
  "blood_pressure_check", "glucose_check",
  // Movement and exercise
  "walking", "exercising", "stretching", "physical_therapy",
  // Leisure
  "watching_tv", "reading", "socializing", "phone_call", "gardening",
  // Safety / location events
  "left_stove_on", "door_opened", "fall_detected", "bathroom_occupancy",
  // Cognitive companion specific
  "meal_lunch", "meal_dinner", "meal_breakfast",
];

// Step type metadata cache (for defaults)
const stepTypeDefaults = ref({});

// Hardcoded defaults (used if API fails)
const fallbackDefaults = {
  person_identification: {
    target_persons: [],
    min_confidence: 0.6,
    include_annotated_image: true,
    include_motion: false,
    save_guest_images: false,
    additional_sensor_ids: [],
  },
  vision_analysis: {
    prompt: "",
    use_annotated_image: false,
    image_source: "trigger",
    max_images: 5,
    additional_sensor_ids: [],
    additional_room_names: [],
    image_time_filter: {},
    response_format: "default",
    response_schema: "",
    response_json_schema: "",
    thinking: false,
    temperature: null,
    top_p: null,
    max_tokens: null,
  },
  notification: {
    alert_level: "warning",
    channels: [],
    message_template: "",
    telegram_template: "",
    eink_template: "",
    ha_speaker_tts_template: "",
    pwa_popup_text_template: "",
    pwa_realtime_ai_template: "",
    webhook_template: "",
    webhook_url: "",
    eink_targets: [],
    eink_template_id: null,
    eink_expiry_minutes: 30,
    ha_media_player: "",
    tts_language: "",
    tts_style: "",
    trigger_cooloff: true,
    telegram_image_source: "trigger",
    telegram_additional_sensor_ids: [],
    telegram_additional_room_names: [],
    telegram_images_per_sensor: 1,
    telegram_sort_by_sensor_then_time: false,
    telegram_image_time_filter: {},
  },
  ha_action: {
    domain: "",
    service: "",
    entity_id: "",
    data: "",
    trigger_cooloff: true,
  },
  activity_detection: {
    activity_type: "",
    person_id: "",
    confidence: "0.8",
    room_name: "",
    capture_scene_description: false,
    scene_description_key: "vision_response",
    metadata_extra: "",
    trigger_cooloff: true,
  },
  wait: {
    minutes: 5,
  },
  condition: {
    expression: "",
    trigger_cooloff: false,
  },
  verification: {
    conditions: [],
    match_mode: "all",
    re_notify_if_failed: false,
    re_notify_delay_minutes: 5,
  },
  llm_call: {
    model_id: "",
    prompt: "",
    include_context: [],
    image_source: "none",
    max_images: 5,
    additional_sensor_ids: [],
    additional_room_names: [],
    images_per_sensor: 3,
    sort_by_sensor_then_time: false,
    image_time_filter: {},
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
  },
};

onMounted(async () => {
  try {
    const types = await api.getStepTypes();
    for (const t of types) {
      stepTypeDefaults.value[t.type_name] = t.default_config || {};
    }
  } catch {
    // Use fallback defaults
  }
  try {
    const channels = await api.getChannelTypes();
    availableChannels.value = channels.map((c) => c.channel_name);
  } catch {
    // Use fallback channel list
  }
  try {
    const persons = await api.getPersons();
    availablePersons.value = persons.map((p) => p.id);
  } catch {
    // Persons list unavailable
  }
  try {
    const rooms = await api.getRooms();
    availableRooms.value = rooms.map((r) => r.name);
  } catch {
    // Rooms list unavailable
  }
  try {
    const sensors = await api.getSensors();
    availableSensors.value = sensors;
    einkSensorItems.value = sensors
      .filter((s) => s.sensor_type === "eink")
      .map((s) => s.id);
    cameraSensorItems.value = sensors
      .filter((s) => s.sensor_type === "camera")
      .map((s) => s.id);
  } catch {
    // Sensors list unavailable
  }
  try {
    haMediaPlayerItems.value = await api.getHAMediaPlayers();
  } catch {
    // HA not configured or unavailable
  }
  try {
    llmModelItems.value = await api.getLLMModels();
  } catch {
    // Registry unavailable
  }
  try {
    imageTemplateItems.value = await api.getImageTemplates();
  } catch {
    // Registry unavailable
  }
});

function getDefaults(stepType) {
  // Prefer API-provided defaults, fall back to hardcoded
  return stepTypeDefaults.value[stepType] || fallbackDefaults[stepType] || {};
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

    // Populate imageTimeFilter for vision_analysis
    if (step.step_type === "vision_analysis") {
      const tf = incoming.image_time_filter || {};
      imageTimeFilter.since_minutes = tf.since_minutes || null;
      imageTimeFilter.time_start = tf.time_start || "";
      imageTimeFilter.time_end = tf.time_end || "";
    }

    // Populate llmImageTimeFilter for llm_call
    if (step.step_type === "llm_call") {
      const tf = incoming.image_time_filter || {};
      llmImageTimeFilter.since_minutes = tf.since_minutes || null;
      llmImageTimeFilter.time_start = tf.time_start || "";
      llmImageTimeFilter.time_end = tf.time_end || "";
      if (cfg.response_json_schema) {
        try {
          JSON.parse(cfg.response_json_schema);
          llmJsonSchemaError.value = "";
        } catch (e) {
          llmJsonSchemaError.value = "Invalid JSON: " + e.message;
        }
      }
    }

    // Populate notificationImageTimeFilter for notification
    if (step.step_type === "notification") {
      const tf = incoming.telegram_image_time_filter || {};
      notificationImageTimeFilter.since_minutes = tf.since_minutes || null;
      notificationImageTimeFilter.time_start = tf.time_start || "";
      notificationImageTimeFilter.time_end = tf.time_end || "";
    }

    // Validate response_json_schema for vision_analysis
    if (step.step_type === "vision_analysis" && cfg.response_json_schema) {
      try {
        JSON.parse(cfg.response_json_schema);
        jsonSchemaError.value = "";
      } catch (e) {
        jsonSchemaError.value = "Invalid JSON: " + e.message;
      }
    }

    // Add _time_mode and _window_*_time helpers to verification conditions for UI
    if (step.step_type === "verification" && Array.isArray(cfg.conditions)) {
      cfg.conditions = cfg.conditions.map((c) => ({
        room_name: "",
        ...c,
        _time_mode: c.window_start || c.window_end ? "fixed" : "relative",
        _window_start_time: c.window_start ? isoToTimeStr(c.window_start) : "",
        _window_end_time: c.window_end ? isoToTimeStr(c.window_end) : "",
      }));
    }

    // Normalize target_persons to array for person_identification combobox
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

    // For unknown/plugin types, show JSON editor
    if (!knownTypes.includes(step.step_type) && step.step_type) {
      genericConfigJson.value = JSON.stringify(incoming, null, 2);
      genericConfigError.value = "";
    }
  },
  { immediate: true }
);

// Load HA entities when the ha_action domain field changes.
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

/**
 * Extract "HH:MM" from a UTC ISO-8601 string, displayed in the app timezone.
 * Delegates to the centralised timezone utility so the result is consistent
 * with the configured ``app.timezone``.
 */
const isoToTimeStr = isoToLocalHHMM;

/**
 * Build a UTC ISO-8601 string for today at the given "HH:MM" time in the app
 * timezone.  Delegates to the centralised timezone utility which handles DST.
 */
const timeStrToTodayISO = localHHMMToUTCISO;

const STEP_LABELS = {
  activity_detection: "Record Activity",
  verification: "Verify Activity",
  person_identification: "Person Identification",
};

function humanize(type) {
  if (!type) return "Step";
  if (STEP_LABELS[type]) return STEP_LABELS[type];
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function capabilityColor(cap) {
  return { text: "primary", vision: "indigo", translation: "teal" }[cap] || "grey";
}

function addCondition() {
  if (!cfg.conditions) cfg.conditions = [];
  cfg.conditions.push({
    person_id: "",
    activity_type: "",
    room_name: "",
    completed: true,
    _time_mode: "relative",
    within_minutes: 30,
    window_start: null,
    window_end: null,
    _window_start_time: "",
    _window_end_time: "",
    min_confidence: 0.5,
  });
}

function formatTemplateToken(key) {
  return `{{${key}}}`;
}

/** Copy a templating token like {{key}} to the clipboard for paste-into-prompt. */
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

function save() {
  let config;

  // For unknown/plugin types, parse JSON
  if (!knownTypes.includes(localStep.step_type) && localStep.step_type) {
    try {
      config = JSON.parse(genericConfigJson.value);
      genericConfigError.value = "";
    } catch (e) {
      genericConfigError.value = "Invalid JSON: " + e.message;
      return;
    }
  } else {
    config = { ...cfg };

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

    // Convert verification conditions: time inputs -> ISO timestamps, strip UI fields
    if (localStep.step_type === "verification" && Array.isArray(config.conditions)) {
      config.conditions = config.conditions.map(({ _time_mode, _window_start_time, _window_end_time, ...rest }) => {
        if (_time_mode === "fixed") {
          rest.window_start = timeStrToTodayISO(_window_start_time);
          rest.window_end = timeStrToTodayISO(_window_end_time);
          delete rest.within_minutes;
        } else {
          delete rest.window_start;
          delete rest.window_end;
        }
        return rest;
      });
    }

    // Merge imageTimeFilter into vision_analysis config
    if (localStep.step_type === "vision_analysis") {
      const tf = {};
      if (imageTimeFilter.since_minutes) tf.since_minutes = imageTimeFilter.since_minutes;
      if (imageTimeFilter.time_start) tf.time_start = imageTimeFilter.time_start;
      if (imageTimeFilter.time_end) tf.time_end = imageTimeFilter.time_end;
      config.image_time_filter = Object.keys(tf).length > 0 ? tf : {};
    }

    // Merge llmImageTimeFilter into llm_call config
    if (localStep.step_type === "llm_call") {
      const tf = {};
      if (llmImageTimeFilter.since_minutes) tf.since_minutes = llmImageTimeFilter.since_minutes;
      if (llmImageTimeFilter.time_start) tf.time_start = llmImageTimeFilter.time_start;
      if (llmImageTimeFilter.time_end) tf.time_end = llmImageTimeFilter.time_end;
      config.image_time_filter = Object.keys(tf).length > 0 ? tf : {};

      if (config.response_json_schema) {
        try {
          JSON.parse(config.response_json_schema);
          llmJsonSchemaError.value = "";
        } catch (e) {
          llmJsonSchemaError.value = "Invalid JSON: " + e.message;
          return;
        }
      }
    }

    // Merge notificationImageTimeFilter into notification config
    if (localStep.step_type === "notification") {
      const tf = {};
      if (notificationImageTimeFilter.since_minutes) tf.since_minutes = notificationImageTimeFilter.since_minutes;
      if (notificationImageTimeFilter.time_start) tf.time_start = notificationImageTimeFilter.time_start;
      if (notificationImageTimeFilter.time_end) tf.time_end = notificationImageTimeFilter.time_end;
      config.telegram_image_time_filter = Object.keys(tf).length > 0 ? tf : {};
    }

    // Validate JSON schema for vision_analysis
    if (localStep.step_type === "vision_analysis" && config.response_json_schema) {
      try {
        JSON.parse(config.response_json_schema);
        jsonSchemaError.value = "";
      } catch (e) {
        jsonSchemaError.value = "Invalid JSON: " + e.message;
        return;
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
  }

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
  min-width: 0;
}

/* Vuetify's v-window clips overflow for slide transitions, which cuts off
   the top of floating labels and hints on the first form field. Allow
   overflow so labels render fully; the scroll container above handles clipping. */
.step-config-content :deep(.v-window),
.step-config-content :deep(.v-window__container) {
  overflow: visible !important;
}

.step-config-vars {
  width: 300px;
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
</style>
