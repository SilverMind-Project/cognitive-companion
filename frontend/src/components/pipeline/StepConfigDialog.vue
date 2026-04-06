<template>
  <v-dialog :model-value="modelValue" max-width="640" scrollable @update:model-value="$emit('update:modelValue', $event)">
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-cog</v-icon>
        Configure {{ humanize(localStep.step_type) }}
      </v-card-title>

      <v-card-text>
        <!-- Common: label -->
        <v-text-field
          v-model="localStep.label"
          label="Step Label"
          variant="outlined"
          density="comfortable"
          hint="Optional display name for this step"
          persistent-hint
          class="mb-4"
        />

        <!-- person_identification -->
        <template v-if="localStep.step_type === 'person_identification'">
          <v-combobox
            v-model="cfg.target_persons"
            :items="availablePersons"
            label="Target Persons"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Select persons to identify, or leave empty for all"
            persistent-hint
            class="mb-3"
          />
          <v-slider
            v-model="cfg.min_confidence"
            label="Min Confidence"
            :min="0"
            :max="1"
            :step="0.05"
            thumb-label="always"
            color="primary"
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.include_annotated_image"
            label="Include annotated image"
            density="comfortable"
            hide-details
          />
          <v-checkbox
            v-model="cfg.include_motion"
            label="Include motion data"
            density="comfortable"
            hide-details
          />
          <v-checkbox
            v-model="cfg.save_guest_images"
            label="Save guest images (unidentified faces)"
            density="comfortable"
            hide-details
          />
        </template>

        <!-- llm_call -->
        <template v-if="localStep.step_type === 'llm_call'">
          <!-- Model selector -->
          <v-select
            v-model="cfg.model_id"
            :items="llmModelItems"
            :item-title="(m) => m.name || m.id"
            :item-value="(m) => m.id"
            label="Model"
            variant="outlined"
            density="comfortable"
            hint="Select a model from the registry (settings.yaml → llm.models)"
            persistent-hint
            class="mb-3"
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

          <!-- Selected model capabilities summary -->
          <div v-if="selectedLLMModel" class="d-flex ga-1 mb-3 flex-wrap">
            <v-chip
              v-for="cap in selectedLLMModel.capabilities"
              :key="cap"
              size="small"
              :color="capabilityColor(cap)"
              variant="tonal"
            >{{ cap }}</v-chip>
            <v-chip size="small" variant="outlined" class="ml-1">{{ selectedLLMModel.api_type }}</v-chip>
            <v-chip v-if="selectedLLMModel.guided_decoding" size="small" color="success" variant="tonal">guided decoding</v-chip>
          </div>

          <!-- Prompt -->
          <v-textarea
            v-model="cfg.prompt"
            label="Prompt"
            variant="outlined"
            rows="4"
            class="mb-3"
            hint="Use {{variable}} for template values, e.g. {{person_detections.0.name}}, {{vision_response}}"
            persistent-hint
          />

          <!-- Special instructions (translation style, etc.) -->
          <v-textarea
            v-model="cfg.special_instructions"
            label="Special Instructions (prepended to prompt)"
            variant="outlined"
            rows="2"
            hint="Prepended before the prompt. Useful for style guides, translation instructions, etc."
            persistent-hint
            class="mb-3"
          />

          <!-- Context keys -->
          <v-combobox
            v-model="cfg.include_context"
            :items="contextKeys"
            label="Include Context Keys"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Pipeline data keys to include as context above the prompt"
            persistent-hint
            class="mb-3"
          />

          <!-- Vision / image options (shown only when model has vision capability) -->
          <template v-if="selectedLLMModel && selectedLLMModel.capabilities.includes('vision')">
            <v-divider class="mb-3" />
            <div class="text-subtitle-2 mb-2">
              <v-icon size="small" class="mr-1">mdi-camera</v-icon>
              Image Inputs
            </div>

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
              variant="outlined"
              density="comfortable"
              hint="Which images to attach to the prompt"
              persistent-hint
              class="mb-3"
            />

            <v-text-field
              v-if="cfg.image_source !== 'none'"
              v-model.number="cfg.max_images"
              label="Max Images (total)"
              variant="outlined"
              density="comfortable"
              type="number"
              :min="1"
              hint="Hard cap on total images sent to the model"
              persistent-hint
              class="mb-3"
            />

            <!-- Additional camera configuration -->
            <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
              <v-combobox
                v-model="cfg.additional_sensor_ids"
                :items="cameraSensorItems"
                label="Camera Sensors (in analysis order)"
                variant="outlined"
                density="comfortable"
                multiple
                chips
                closable-chips
                hint="Sensors are processed in the order listed. Determines grouping when 'Sort by sensor' is on."
                persistent-hint
                class="mb-3"
              />
              <v-combobox
                v-model="cfg.additional_room_names"
                :items="availableRooms"
                label="Additional Rooms"
                variant="outlined"
                density="comfortable"
                multiple
                chips
                closable-chips
                hint="Pull images from all cameras in these rooms (unordered)"
                persistent-hint
                class="mb-3"
              />

              <!-- Sensor-ordered grouping for inter-frame analysis -->
              <v-card variant="tonal" class="mb-3 pa-3">
                <v-checkbox
                  v-model="cfg.sort_by_sensor_then_time"
                  label="Group by sensor, then chronological within each sensor"
                  density="comfortable"
                  hide-details
                  class="mb-2"
                />
                <div class="text-caption text-medium-emphasis ml-8">
                  Enables inter-frame temporal analysis. Images are ordered:
                  all frames from sensor 1 (oldest→newest), then sensor 2, etc.
                  Sensor order follows the Camera Sensors list above.
                </div>
                <v-text-field
                  v-if="cfg.sort_by_sensor_then_time"
                  v-model.number="cfg.images_per_sensor"
                  label="Images per sensor"
                  variant="outlined"
                  density="compact"
                  type="number"
                  :min="1"
                  hint="Maximum frames to include from each sensor"
                  persistent-hint
                  class="mt-3"
                />
              </v-card>

              <!-- Time filter for additional images -->
              <v-expansion-panels variant="accordion" class="mb-3">
                <v-expansion-panel>
                  <v-expansion-panel-title class="text-body-2">
                    <v-icon class="mr-2" size="small">mdi-clock-outline</v-icon>
                    Time Filter (optional)
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <v-text-field
                      v-model.number="llmImageTimeFilter.since_minutes"
                      label="Since (minutes ago)"
                      variant="outlined"
                      density="comfortable"
                      type="number"
                      :min="0"
                      hint="Only include images from the last N minutes"
                      persistent-hint
                      class="mb-3"
                    />
                    <v-text-field
                      v-model="llmImageTimeFilter.time_start"
                      label="Time Start (HH:MM)"
                      variant="outlined"
                      density="comfortable"
                      placeholder="e.g. 08:00"
                      class="mb-3"
                    />
                    <v-text-field
                      v-model="llmImageTimeFilter.time_end"
                      label="Time End (HH:MM)"
                      variant="outlined"
                      density="comfortable"
                      placeholder="e.g. 18:00"
                    />
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </template>
          </template>

          <!-- Response format -->
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 mb-2">
            <v-icon size="small" class="mr-1">mdi-code-json</v-icon>
            Output Format
          </div>

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
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />

          <template v-if="cfg.response_format === 'json_schema' || cfg.response_format === 'json_free'">
            <v-textarea
              v-model="cfg.response_schema"
              label="Format Instruction (appended to prompt)"
              variant="outlined"
              rows="2"
              hint="Natural-language description of expected JSON keys, appended to the prompt"
              persistent-hint
              class="mb-3"
            />
          </template>
          <template v-if="cfg.response_format === 'json_schema'">
            <v-textarea
              v-model="cfg.response_json_schema"
              label="JSON Schema"
              variant="outlined"
              rows="6"
              :hint="selectedLLMModel && selectedLLMModel.guided_decoding
                ? 'Schema enforced via guided decoding (vLLM). Leave empty to rely on prompt instruction only.'
                : 'Schema injected as a prompt instruction (this model does not support guided decoding).'"
              persistent-hint
              :error-messages="llmJsonSchemaError"
              class="mb-3"
            />
          </template>

          <!-- Output key -->
          <v-text-field
            v-model="cfg.output_key"
            label="Output Key"
            variant="outlined"
            density="comfortable"
            hint="Pipeline data key for the result. Use 'logic_response', 'vision_response', or 'translation' for downstream step compatibility."
            persistent-hint
            class="mb-3"
          />

          <!-- Hallucination retry -->
          <v-expansion-panels variant="accordion" class="mb-3">
            <v-expansion-panel>
              <v-expansion-panel-title class="text-body-2">
                <v-icon class="mr-2" size="small">mdi-refresh-auto</v-icon>
                Hallucination Retry (optional)
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-text-field
                  v-model="cfg.hallucination_marker"
                  label="Hallucination Marker"
                  variant="outlined"
                  density="comfortable"
                  hint="If this string appears in the response, the call is automatically retried."
                  persistent-hint
                />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </template>

        <!-- vision_analysis -->
        <template v-if="localStep.step_type === 'vision_analysis'">
          <v-textarea
            v-model="cfg.prompt"
            label="Vision Prompt"
            variant="outlined"
            rows="4"
            class="mb-3"
            hint="Use {{variable}} for template values, e.g. {{person_detections.0.name}}, {{room_name}}"
            persistent-hint
          />
          <v-checkbox
            v-model="cfg.use_annotated_image"
            label="Use annotated image"
            density="comfortable"
            hide-details
            class="mb-3"
          />
          <v-select
            v-model="cfg.image_source"
            :items="['trigger', 'additional', 'both']"
            label="Image Source"
            variant="outlined"
            density="comfortable"
            hint="trigger = frames that triggered pipeline, additional = extra cameras, both = combine"
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model.number="cfg.max_images"
            label="Max Images"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="1"
            hint="Maximum total images sent to the vision model"
            persistent-hint
            class="mb-3"
          />
          <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
            <v-combobox
              v-model="cfg.additional_sensor_ids"
              :items="cameraSensorItems"
              label="Additional Camera Sensors"
              variant="outlined"
              density="comfortable"
              multiple
              chips
              closable-chips
              hint="Extra cameras to pull images from"
              persistent-hint
              class="mb-3"
            />
            <v-combobox
              v-model="cfg.additional_room_names"
              :items="availableRooms"
              label="Additional Rooms"
              variant="outlined"
              density="comfortable"
              multiple
              chips
              closable-chips
              hint="Pull images from all cameras in these rooms"
              persistent-hint
              class="mb-3"
            />
            <v-expansion-panels variant="accordion" class="mb-3">
              <v-expansion-panel>
                <v-expansion-panel-title class="text-body-2">
                  <v-icon class="mr-2" size="small">mdi-clock-outline</v-icon>
                  Time Filter (optional)
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-text-field
                    v-model.number="imageTimeFilter.since_minutes"
                    label="Since (minutes ago)"
                    variant="outlined"
                    density="comfortable"
                    type="number"
                    :min="0"
                    hint="Only include images from the last N minutes"
                    persistent-hint
                    class="mb-3"
                  />
                  <v-text-field
                    v-model="imageTimeFilter.time_start"
                    label="Time Start (HH:MM)"
                    variant="outlined"
                    density="comfortable"
                    placeholder="e.g. 08:00"
                    class="mb-3"
                  />
                  <v-text-field
                    v-model="imageTimeFilter.time_end"
                    label="Time End (HH:MM)"
                    variant="outlined"
                    density="comfortable"
                    placeholder="e.g. 18:00"
                  />
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </template>
          <v-select
            v-model="cfg.response_format"
            :items="['default', 'custom']"
            label="Response Format"
            variant="outlined"
            density="comfortable"
            hint="Controls the structured JSON output enforced on the vision model"
            persistent-hint
            class="mb-3"
          />
          <v-alert v-if="cfg.response_format === 'default'" type="info" variant="tonal" density="compact" class="mb-3">
            <div class="text-subtitle-2 mb-1">Output keys (available as <code>vision_response</code>):</div>
            String (default free-text output)
          </v-alert>
          <template v-if="cfg.response_format === 'custom'">
            <v-textarea
              v-model="cfg.response_schema"
              label="Response Format Instruction"
              variant="outlined"
              rows="3"
              hint="Text instruction appended to the prompt describing expected JSON keys"
              persistent-hint
              class="mb-3"
            />
            <v-textarea
              v-model="cfg.response_json_schema"
              label="JSON Schema (optional)"
              variant="outlined"
              rows="6"
              hint="Paste a JSON Schema to enforce structured output via guided decoding. Leave empty to rely on prompt instruction only."
              persistent-hint
              :error-messages="jsonSchemaError"
              class="mb-3"
            />
          </template>
        </template>

        <!-- logic_reasoning -->
        <template v-if="localStep.step_type === 'logic_reasoning'">
          <v-textarea
            v-model="cfg.prompt"
            label="Reasoning Prompt"
            variant="outlined"
            rows="4"
            class="mb-3"
            hint="Use {{variable}} for template values, e.g. {{vision_response}}, {{person_detections.0.name}}, {{room_name}}"
            persistent-hint
          />
          <v-combobox
            v-model="cfg.include_context"
            :items="contextKeys"
            label="Include Context Keys"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            class="mb-3"
          />
          <v-select
            v-model="cfg.response_format"
            :items="['default', 'activity_detection', 'custom']"
            label="Response Format"
            variant="outlined"
            density="comfortable"
            hint="Controls the structured JSON output enforced on the LLM"
            persistent-hint
            class="mb-3"
          />
          <v-alert v-if="cfg.response_format === 'default'" type="info" variant="tonal" density="compact" class="mb-3">
            <div class="text-subtitle-2 mb-1">Output keys (available as <code>logic_response.*</code>):</div>
            <code>is_notification_needed</code> (bool),
            <code>user_notification</code> (string),
            <code>reasoning</code> (string),
            <code>alert_level</code> (string)
          </v-alert>
          <v-alert v-if="cfg.response_format === 'activity_detection'" type="info" variant="tonal" density="compact" class="mb-3">
            <div class="text-subtitle-2 mb-1">Output keys (available as <code>logic_response.*</code>):</div>
            <code>activities</code> (array of {person_id, activity_type, confidence})
          </v-alert>
          <template v-if="cfg.response_format === 'custom'">
            <v-textarea
              v-model="cfg.response_schema"
              label="Response Format Instruction"
              variant="outlined"
              rows="3"
              hint="Text instruction appended to the prompt describing expected JSON keys"
              persistent-hint
              class="mb-3"
            />
            <v-textarea
              v-model="cfg.response_json_schema"
              label="JSON Schema (optional)"
              variant="outlined"
              rows="6"
              hint="Paste a JSON Schema to enforce structured output via guided decoding. Leave empty to rely on prompt instruction only."
              persistent-hint
              :error-messages="jsonSchemaError"
              class="mb-3"
            />
          </template>
        </template>

        <!-- translation -->
        <template v-if="localStep.step_type === 'translation'">
          <v-text-field
            v-model="cfg.target_language"
            label="Target Language"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. es, fr, de, ja"
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.source_text"
            label="Source Text"
            variant="outlined"
            rows="3"
            hint="Text to translate. Supports {{variable}} templates. Leave empty to auto-detect from logic response or vision response."
            persistent-hint
            placeholder="e.g. {{logic_response.user_notification}}"
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.special_instructions"
            label="Special Instructions"
            variant="outlined"
            rows="2"
            hint="Instructions built into the prompt. Useful for guiding language style (e.g. Tanglish)."
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.hallucination_marker"
            label="Hallucination Marker"
            variant="outlined"
            density="comfortable"
            hint="A known string that triggers a retry if found in the response."
            persistent-hint
            class="mb-3"
          />
        </template>

        <!-- notification -->
        <template v-if="localStep.step_type === 'notification'">
          <v-select
            v-model="cfg.alert_level"
            :items="['emergency', 'warning', 'info', 'reminder']"
            label="Alert Level"
            variant="outlined"
            density="comfortable"
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.channels"
            :items="availableChannels"
            label="Notification Channels"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Select channels or type custom channel names"
            persistent-hint
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.message_template"
            label="Message Template (default)"
            variant="outlined"
            rows="3"
            hint="Default template for all channels. Use {message}, {room}, {vision_response}, etc."
            persistent-hint
            class="mb-3"
          />
          <v-expansion-panels variant="accordion" class="mb-3">
            <v-expansion-panel>
              <v-expansion-panel-title class="text-body-2">
                <v-icon class="mr-2" size="small">mdi-message-text-outline</v-icon>
                Per-Channel Templates (optional)
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-textarea
                  v-model="cfg.telegram_template"
                  label="Telegram Template"
                  variant="outlined"
                  rows="3"
                  hint="HTML template for Telegram. Use {message}, {room}, etc. Falls back to Message Template."
                  persistent-hint
                  class="mb-3"
                />
                <v-textarea
                  v-model="cfg.eink_template"
                  label="E-Ink Template"
                  variant="outlined"
                  rows="2"
                  hint="Short plain-text for e-ink displays. Falls back to Message Template."
                  persistent-hint
                  class="mb-3"
                />
                <v-textarea
                  v-model="cfg.tts_template"
                  label="TTS Template"
                  variant="outlined"
                  rows="2"
                  hint="Natural language for spoken announcements. Falls back to Message Template."
                  persistent-hint
                  class="mb-3"
                />
                <v-textarea
                  v-model="cfg.websocket_template"
                  label="WebSocket Template"
                  variant="outlined"
                  rows="2"
                  hint="Notification text shown in the companion UI overlay. Use {message}, {room}, etc. Falls back to Message Template."
                  persistent-hint
                  class="mb-3"
                />
                <v-textarea
                  v-model="cfg.realtime_voice_template"
                  label="Realtime Voice Template"
                  variant="outlined"
                  rows="2"
                  hint="Conversational voice prompt for Gemini Live delivery. Falls back to Message Template."
                  persistent-hint
                />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <v-combobox
            v-model="cfg.eink_targets"
            :items="einkSensorItems"
            label="E-Ink Target Devices"
            variant="outlined"
            density="comfortable"
            multiple
            chips
            closable-chips
            hint="Select eink displays (empty = all eink devices)"
            persistent-hint
          />
          <v-autocomplete
            v-if="cfg.channels && cfg.channels.includes('tts')"
            v-model="cfg.ha_media_player"
            :items="haMediaPlayerItems"
            :item-title="(item) => item.name || item.entity_id || item"
            :item-value="(item) => item.entity_id || item"
            label="TTS Media Player"
            variant="outlined"
            density="comfortable"
            clearable
            hint="Home Assistant media_player entity for TTS audio playback"
            persistent-hint
            class="mt-3"
          />
          <v-text-field
            v-if="cfg.channels && cfg.channels.includes('tts')"
            v-model="cfg.tts_language"
            label="TTS Language"
            variant="outlined"
            density="comfortable"
            clearable
            placeholder="e.g. ta, en"
            hint="Language code for TTS synthesis. Leave blank to use the server default."
            persistent-hint
            class="mt-3"
          />
          <v-select
            v-if="cfg.channels && cfg.channels.includes('tts')"
            v-model="cfg.tts_style"
            :items="['', 'neutral', 'clear', 'formal', 'chat', 'happy', 'surprise', 'sad', 'fear', 'anger', 'disgust', 'narrative', 'enthusiastic', 'laugh', 'yawn', 'angry']"
            label="TTS Style"
            variant="outlined"
            density="comfortable"
            clearable
            hint="Svara speaking style. Leave blank to use the server default."
            persistent-hint
            class="mt-3"
          />
          <template v-if="cfg.channels && cfg.channels.includes('webhook')">
            <v-text-field
              v-model="cfg.webhook_url"
              label="Webhook URL (optional)"
              variant="outlined"
              density="comfortable"
              clearable
              hint="Override global webhook endpoint (from settings/env)"
              persistent-hint
              class="mt-3"
            />
            <v-textarea
              v-model="cfg.webhook_template"
              label="Webhook JSON Template (optional)"
              variant="outlined"
              rows="4"
              hint="JSON payload template. Uses {message}, {room}, etc. Fallback to basic JSON."
              persistent-hint
              class="mt-3"
            />
          </template>
          <v-checkbox
            v-model="cfg.trigger_cooloff"
            label="Trigger rate-limit cool-off upon execution"
            density="comfortable"
            hide-details
            class="mt-3 mb-3"
          />
        </template>

        <!-- ha_action -->
        <template v-if="localStep.step_type === 'ha_action'">
          <v-text-field
            v-model="cfg.domain"
            label="Domain"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. light, switch, script"
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.service"
            label="Service"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. turn_on, toggle"
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.entity_id"
            :items="haEntityItems"
            :item-title="(item) => item.name ? `${item.name} (${item.entity_id})` : (item.entity_id || item)"
            :item-value="(item) => item.entity_id || item"
            label="Entity ID"
            variant="outlined"
            density="comfortable"
            placeholder="e.g. light.living_room"
            hint="Select from discovered entities or type an entity ID"
            persistent-hint
            class="mb-3"
          />
          <v-textarea
            v-model="cfg.data"
            label="Service Data (JSON)"
            variant="outlined"
            rows="3"
            placeholder='{ "brightness": 255 }'
          />
        </template>

        <!-- activity_detection -->
        <template v-if="localStep.step_type === 'activity_detection'">
          <v-combobox
            v-model="cfg.activity_type"
            :items="activityTypes"
            label="Activity Type"
            variant="outlined"
            density="comfortable"
            hint="Activity to record. Supports {{template}} syntax (e.g. {{logic_response.activity_type}})."
            persistent-hint
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.person_id"
            :items="availablePersons"
            label="Person ID (optional)"
            variant="outlined"
            density="comfortable"
            clearable
            hint="Person to attribute this activity to. Supports {{template}} syntax (e.g. {{person_detections.0.person_id}}). Leave empty for unknown person."
            persistent-hint
            class="mb-3"
          />
          <v-combobox
            v-model="cfg.room_name"
            :items="availableRooms"
            label="Room (optional)"
            variant="outlined"
            density="comfortable"
            clearable
            hint="Room where the activity occurred. Supports {{template}} syntax (e.g. {{room_name}}). Defaults to trigger room when empty."
            persistent-hint
            class="mb-3"
          />
          <v-text-field
            v-model="cfg.confidence"
            label="Confidence"
            variant="outlined"
            density="comfortable"
            hint="Fixed value (0-1) or {{template}} syntax (e.g. {{logic_response.confidence}}). Defaults to 0.8."
            persistent-hint
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.trigger_cooloff"
            label="Trigger rate-limit cool-off upon execution"
            density="comfortable"
            hide-details
            class="mb-3"
          />
        </template>

        <!-- wait -->
        <template v-if="localStep.step_type === 'wait'">
          <v-text-field
            v-model.number="cfg.minutes"
            label="Wait Duration (minutes)"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="0"
          />
        </template>

        <!-- condition -->
        <template v-if="localStep.step_type === 'condition'">
          <v-text-field
            v-model="cfg.expression"
            label="Condition Expression"
            variant="outlined"
            density="comfortable"
            hint="Expression evaluated at runtime to decide if pipeline continues"
            persistent-hint
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.trigger_cooloff"
            label="Trigger rate-limit cool-off if condition is met"
            density="comfortable"
            hide-details
            class="mb-3"
          />
        </template>

        <!-- verification -->
        <template v-if="localStep.step_type === 'verification'">
          <div class="text-subtitle-2 mb-2">Activity Conditions</div>
          <div v-for="(cond, idx) in cfg.conditions" :key="idx" class="mb-4 pa-3 border rounded-lg">
            <div class="d-flex align-center mb-2">
              <span class="text-caption font-weight-bold">Condition {{ idx + 1 }}</span>
              <v-spacer />
              <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="cfg.conditions.splice(idx, 1)" />
            </div>
            <v-combobox
              v-model="cond.person_id"
              :items="availablePersons"
              label="Person ID (optional)"
              variant="outlined"
              density="compact"
              clearable
              hint="Leave empty to match any person. Supports {{template}} syntax."
              persistent-hint
              class="mb-2"
            />
            <v-combobox
              v-model="cond.activity_type"
              :items="activityTypes"
              label="Activity Type"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-combobox
              v-model="cond.room_name"
              :items="availableRooms"
              label="Room (optional)"
              variant="outlined"
              density="compact"
              clearable
              hint="Leave empty to match any room. Supports {{template}} syntax (e.g. {{room_name}})."
              persistent-hint
              class="mb-2"
            />
            <v-checkbox
              v-model="cond.completed"
              label="Expect completed (uncheck to verify NOT done)"
              density="compact"
              hide-details
              class="mb-2"
            />
            <v-select
              v-model="cond._time_mode"
              :items="['relative', 'fixed']"
              label="Time Window"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-text-field
              v-if="cond._time_mode !== 'fixed'"
              v-model.number="cond.within_minutes"
              label="Within Minutes"
              variant="outlined"
              density="compact"
              type="number"
              :min="0"
              class="mb-2"
            />
            <template v-if="cond._time_mode === 'fixed'">
              <v-text-field
                v-model="cond._window_start_time"
                label="Start Time (today)"
                variant="outlined"
                density="compact"
                type="time"
                hint="Start time for today's window"
                persistent-hint
                class="mb-2"
              />
              <v-text-field
                v-model="cond._window_end_time"
                label="End Time (today)"
                variant="outlined"
                density="compact"
                type="time"
                hint="End time for today's window"
                persistent-hint
                class="mb-2"
              />
            </template>
            <v-slider
              v-model="cond.min_confidence"
              label="Min Confidence"
              :min="0"
              :max="1"
              :step="0.05"
              thumb-label="always"
              color="primary"
            />
          </div>
          <v-btn variant="tonal" prepend-icon="mdi-plus" class="mb-4" @click="addCondition">
            Add Condition
          </v-btn>

          <v-select
            v-model="cfg.match_mode"
            :items="['all', 'any']"
            label="Match Mode"
            variant="outlined"
            density="comfortable"
            hint="'all' = every condition must pass, 'any' = at least one"
            persistent-hint
            class="mb-3"
          />
          <v-checkbox
            v-model="cfg.re_notify_if_failed"
            label="Re-notify if verification fails"
            density="comfortable"
            hide-details
            class="mb-3"
          />
          <v-text-field
            v-model.number="cfg.re_notify_delay_minutes"
            label="Re-notify Delay (minutes)"
            variant="outlined"
            density="comfortable"
            type="number"
            :min="0"
          />
        </template>

        <!-- Generic fallback for unknown/plugin step types -->
        <template v-if="!knownTypes.includes(localStep.step_type) && localStep.step_type">
          <v-alert type="info" variant="tonal" class="mb-3">
            This step type uses a plugin configuration. Edit the JSON config below.
          </v-alert>
          <v-textarea
            v-model="genericConfigJson"
            label="Config JSON"
            variant="outlined"
            rows="8"
            class="mb-3"
            :error-messages="genericConfigError"
          />
        </template>

        <!-- Pipeline Data Reference (shown for all step types) -->
        <v-expansion-panels v-if="localStep.step_type" variant="accordion" class="mt-4">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-body-2">
              <v-icon class="mr-2" size="small">mdi-code-braces</v-icon>
              Pipeline Data Reference
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-alert type="info" variant="tonal" density="compact" class="mb-3">
                These keys are available from upstream steps. Use them in prompts as
                <code>{{key}}</code> or in templates as <code>{key}</code>.
              </v-alert>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Type</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in pipelineDataReference" :key="item.key">
                    <td><code>{{ item.key }}</code></td>
                    <td class="text-caption">{{ item.type }}</td>
                    <td class="text-caption">{{ item.source }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" @click="save">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch, reactive, computed, onMounted } from "vue";
import { api } from "../../services/api.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  step: { type: Object, default: null },
});

const emit = defineEmits(["update:modelValue", "save"]);

const knownTypes = [
  "llm_call",
  "person_identification", "vision_analysis", "logic_reasoning",
  "translation", "notification", "ha_action", "activity_detection",
  "wait", "condition", "verification",
];

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
const llmJsonSchemaError = ref("");
const cameraSensorItems = ref([]);

// LLM model registry (for the llm_call step)
const llmModelItems = ref([]);
const selectedLLMModel = computed(() =>
  llmModelItems.value.find((m) => m.id === cfg.model_id) || null
);

// Pipeline data reference for the info panel
const pipelineDataReference = [
  { key: "trigger.sensor_id", type: "string", source: "Trigger context" },
  { key: "trigger.room_name", type: "string", source: "Trigger context" },
  { key: "trigger.media_paths", type: "string[]", source: "Trigger context" },
  { key: "person_detections", type: "array of {name, person_id, confidence, bbox}", source: "person_identification" },
  { key: "annotated_image", type: "string (base64)", source: "person_identification" },
  { key: "vision_response", type: "string", source: "vision_analysis" },
  { key: "logic_response", type: "object (schema depends on response_format)", source: "logic_reasoning" },
  { key: "logic_response.is_notification_needed", type: "boolean", source: "logic_reasoning (default)" },
  { key: "logic_response.user_notification", type: "string", source: "logic_reasoning (default)" },
  { key: "logic_response.alert_level", type: "string", source: "logic_reasoning (default)" },
  { key: "translation", type: "string", source: "translation" },
  { key: "detected_activities", type: "array", source: "activity_detection" },
  { key: "verification", type: "object {verified, matched_conditions}", source: "verification" },
  { key: "notification_dispatched", type: "boolean", source: "notification" },
  { key: "notification_channels", type: "object {channel: bool}", source: "notification" },
];

// Dynamic lists from API
const availableChannels = ref(["websocket", "telegram", "eink", "tts", "webhook"]);
const availablePersons = ref([]);
const availableRooms = ref([]);
const availableSensors = ref([]);
const einkSensorItems = ref([]);
const haMediaPlayerItems = ref([]);
const haEntityItems = ref([]);
const activityTypes = [
  "eating", "sleeping", "medication", "bathing", "walking",
  "watching_tv", "reading", "exercising", "cooking", "socializing",
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
  },
  logic_reasoning: {
    prompt: "",
    include_context: [],
    response_format: "default",
    response_schema: "",
    response_json_schema: "",
  },
  translation: {
    target_language: "ta",
    source_text: "",
    hallucination_marker: "சென்னை",
    special_instructions: "Translate using informal Tamil that is spoken in Chennai (i.e Tamil mixed with English):  \n",
  },
  notification: {
    alert_level: "warning",
    channels: [],
    message_template: "",
    telegram_template: "",
    eink_template: "",
    tts_template: "",
    webhook_template: "",
    webhook_url: "",
    eink_targets: [],
    ha_media_player: "",
    tts_language: "",
    tts_style: "",
    trigger_cooloff: true,
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

    // Validate response_json_schema for logic_reasoning and vision_analysis
    if ((step.step_type === "logic_reasoning" || step.step_type === "vision_analysis") && cfg.response_json_schema) {
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

/** Extract "HH:MM" from an ISO-8601 datetime string. */
function isoToTimeStr(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return "";
  }
}

/** Build an ISO-8601 UTC string for today at the given "HH:MM" local time. */
function timeStrToTodayISO(timeStr) {
  if (!timeStr) return null;
  const [h, m] = timeStr.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}

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

    // Validate JSON schema for logic_reasoning and vision_analysis
    if ((localStep.step_type === "logic_reasoning" || localStep.step_type === "vision_analysis") && config.response_json_schema) {
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
