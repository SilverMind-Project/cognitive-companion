<template>
  <v-dialog
    :model-value="modelValue"
    width="1440"
    max-width="98vw"
    :fullscreen="$vuetify.display.smAndDown"
    scrollable
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card class="cc-glass step-config-card d-flex flex-column">
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
                  hint="Used as the key in pipeline_data.steps — must be unique, lowercase, letters/digits/underscores only"
                  persistent-hint
                  :rules="labelRules"
                  :error-messages="labelUniqueError"
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
                  <v-textarea
                    v-model="cfg.expression"
                    label="Condition Expression"
                    :rows="3"
                    auto-grow
                    hint="Evaluated at runtime — true branch continues, false branch stops or takes the alternate path."
                    persistent-hint
                    class="mb-4 condition-expression-textarea"
                  />

                  <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-body-2">
                    <strong>No <code>{{ }}</code> curly braces needed.</strong>
                    Write expressions directly using dotted paths
                    (<code>steps.my_step.outputs.field</code>), comparison operators, and
                    <code>and</code> / <code>or</code> / <code>not</code>.
                    Use <code>jq("...")</code> with JMESPath syntax to filter and count arrays,
                    and <code>icontains(path, "text")</code> for case-insensitive string checks.
                    Step labels in expressions must match the labels you assigned your steps.
                  </v-alert>

                  <v-expansion-panels variant="accordion" class="mb-4">
                    <v-expansion-panel>
                      <v-expansion-panel-title class="text-body-2 font-weight-medium">
                        <v-icon size="small" class="mr-2">mdi-code-tags</v-icon>
                        Examples — click any to load into the expression field
                      </v-expansion-panel-title>
                      <v-expansion-panel-text class="pa-0">
                        <v-list density="compact" class="condition-examples-list">
                          <v-list-item
                            v-for="ex in conditionExamples"
                            :key="ex.label"
                            class="condition-example-row py-2"
                            @click="cfg.expression = ex.expr"
                          >
                            <div class="text-caption font-weight-medium mb-1">{{ ex.label }}</div>
                            <div class="text-caption text-medium-emphasis mb-1">{{ ex.description }}</div>
                            <code class="condition-example-code">{{ ex.expr }}</code>
                          </v-list-item>
                        </v-list>
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>

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

                <!-- scene_analysis -->
                <template v-if="localStep.step_type === 'scene_analysis'">
                  <v-checkbox v-model="cfg.run_detect" label="Run YOLO object detection" hide-details class="mb-1" />
                  <v-checkbox v-model="cfg.run_describe" label="Run Florence-2 scene description" hide-details class="mb-1" />
                  <v-checkbox v-model="cfg.run_hazards" label="Evaluate hazard rules on detections" hide-details class="mb-1" />
                  <v-checkbox v-model="cfg.run_embed" label="Run CLIP embedding (slow)" hide-details class="mb-4" />
                  <v-checkbox v-model="cfg.write_to_memory" label="Write result to semantic memory" hide-details class="mb-2" />
                </template>

                <!-- object_trend_analysis -->
                <template v-if="localStep.step_type === 'object_trend_analysis'">
                  <v-combobox
                    v-model="cfg.room_ids"
                    :items="availableRooms"
                    label="Room IDs"
                    multiple
                    chips
                    closable-chips
                    hint="Rooms to query. Leave empty to use the trigger room."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-select
                    v-model="cfg.severity_threshold"
                    :items="['ok', 'info', 'warning', 'critical']"
                    label="Severity Threshold"
                    hint="Anomalies below this severity are stripped from results."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model.number="cfg.include_snapshots_hours"
                    label="Include Snapshots (hours)"
                    type="number"
                    :min="0"
                    hint="If > 0, fetch raw hourly snapshots for LLM context."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the result map. Default: room_trends"
                    persistent-hint
                  />
                </template>

                <!-- semantic_memory_write -->
                <template v-if="localStep.step_type === 'semantic_memory_write'">
                  <v-select
                    v-model="cfg.write_type"
                    :items="['observation', 'movement']"
                    label="Write Type"
                    hint="What to persist in semantic memory."
                    persistent-hint
                    class="mb-4"
                  />

                  <!-- Observation fields -->
                  <template v-if="cfg.write_type === 'observation'">
                    <v-combobox
                      v-model="cfg.room_id"
                      :items="availableRooms"
                      label="Room ID"
                      hint="Room where the observation occurred."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-textarea
                      v-model="cfg.description"
                      label="Description"
                      rows="3"
                      hint="Human-readable description of the scene."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.object_list"
                      :items="[]"
                      label="Objects Detected"
                      multiple
                      chips
                      closable-chips
                      hint="List of object labels. Supports {{template}} syntax."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.hazard_flags"
                      :items="[]"
                      label="Hazard Flags"
                      multiple
                      chips
                      closable-chips
                      hint="List of hazard flags (e.g. 'door_unsafe', 'person_on_floor')."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-text-field
                      v-model="cfg.source"
                      label="Source"
                      hint="Source identifier. Default: scene_intel"
                      persistent-hint
                    />
                  </template>

                  <!-- Movement fields -->
                  <template v-if="cfg.write_type === 'movement'">
                    <v-combobox
                      v-model="cfg.person_id"
                      :items="availablePersons"
                      label="Person ID"
                      hint="Person who moved. Supports {{template}} syntax."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.from_room_id"
                      :items="availableRooms"
                      label="From Room"
                      hint="Starting room. Supports {{template}} syntax."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.to_room_id"
                      :items="availableRooms"
                      label="To Room"
                      hint="Destination room. Supports {{template}} syntax."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.direction_semantic"
                      :items="['entering', 'exiting', 'approaching_exit', 'entering_depth', 'stationary', 'any']"
                      label="Direction Semantic"
                      hint="Type of movement."
                      persistent-hint
                      class="mb-4"
                    />
                    <v-text-field
                      v-model="cfg.confidence"
                      label="Confidence"
                      hint="Confidence score (0-1). Default: 0.8"
                      persistent-hint
                      class="mb-4"
                    />
                    <v-combobox
                      v-model="cfg.observation_id"
                      :items="[]"
                      label="Observation ID (optional)"
                      hint="Link this movement to a prior observation. Supports {{template}} syntax."
                      persistent-hint
                    />
                  </template>
                </template>

                <!-- semantic_memory_query -->
                <template v-if="localStep.step_type === 'semantic_memory_query'">
                  <v-combobox
                    v-model="cfg.room_id"
                    :items="availableRooms"
                    label="Room ID (optional)"
                    clearable
                    hint="Filter by room. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-switch
                    v-model="cfg.use_trigger_room"
                    label="Use trigger room"
                    hint="When enabled, uses the trigger's room instead of the room ID above."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-text-field
                    v-model.number="cfg.since_minutes"
                    label="Lookback (minutes)"
                    type="number"
                    :min="1"
                    hint="How far back to search. Default: 60"
                    persistent-hint
                    class="mb-4"
                  />

                  <v-combobox
                    v-model="cfg.objects_any"
                    :items="[]"
                    label="Objects (any)"
                    multiple
                    chips
                    closable-chips
                    hint="Only include observations containing any of these object labels. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-combobox
                    v-model="cfg.hazard_flags_any"
                    :items="[]"
                    label="Hazard flags (any)"
                    multiple
                    chips
                    closable-chips
                    hint="Only include observations containing any of these hazard flags."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-text-field
                    v-model="cfg.query_text"
                    label="Text query (semantic search)"
                    hint="Free-text query for semantic search. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-text-field
                    v-model.number="cfg.limit"
                    label="Limit"
                    type="number"
                    :min="1"
                    :max="50"
                    hint="Maximum observations to return. Default: 5"
                    persistent-hint
                    class="mb-4"
                  />

                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the result. Default: memory_context"
                    persistent-hint
                  />
                </template>

                <!-- activity_session_start -->
                <template v-if="localStep.step_type === 'activity_session_start'">
                  <v-combobox
                    v-model="cfg.activity_type"
                    :items="activityTypes"
                    label="Activity Type"
                    hint="Supports {{template}} syntax (e.g. {{logic_response.activity_type}})."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.person_id"
                    :items="availablePersons"
                    label="Person ID"
                    clearable
                    hint="Supports {{template}} syntax (e.g. {{person_detections.0.person_id}})."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.room_name"
                    :items="availableRooms"
                    label="Room (optional)"
                    clearable
                    hint="Defaults to trigger room when empty. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.confidence"
                    label="Confidence"
                    hint="Fixed value (0-1) or {{template}} syntax. Default: 0.85."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.timeout_minutes"
                    label="Timeout (minutes, optional)"
                    hint="Max session duration before auto-close. Leave empty for activity-type default."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-textarea
                    v-model="cfg.metadata_extra"
                    label="Extra Metadata (JSON, optional)"
                    rows="3"
                    hint='Optional JSON merged into session metadata. Supports {{template}} syntax.'
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the session result. Default: session"
                    persistent-hint
                  />
                </template>

                <!-- activity_session_end -->
                <template v-if="localStep.step_type === 'activity_session_end'">
                  <v-combobox
                    v-model="cfg.activity_type"
                    :items="activityTypes"
                    label="Activity Type"
                    hint="Activity session to close. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-combobox
                    v-model="cfg.person_id"
                    :items="availablePersons"
                    label="Person ID"
                    clearable
                    hint="Person whose session to close. Supports {{template}} syntax."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox
                    v-model="cfg.write_activity_record"
                    label="Write PersonActivity record with duration"
                    hint="Records a PersonActivity entry with duration_minutes populated."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the closed session result. Default: closed_session"
                    persistent-hint
                  />
                </template>

                <!-- presence_query -->
                <template v-if="localStep.step_type === 'presence_query'">
                  <v-form ref="presenceQueryForm" v-model="presenceQueryValid">
                    <v-combobox
                      v-model="cfg.person_id"
                      :items="availablePersons"
                      label="Person"
                      hint="Person to look up. Supports {{template}} syntax. Leave empty to use the first person found in pipeline_data.persons or pipeline_data.person_id."
                      persistent-hint
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      rounded="lg"
                      clearable
                      class="mb-4"
                      aria-label="Person to look up"
                    />

                    <v-divider class="mb-4" />

                    <div class="text-overline text-medium-emphasis mb-2">Recent dementia signal filter (optional)</div>

                    <v-combobox
                      v-model="cfg.signal_kind"
                      :items="knownSignalKinds"
                      label="Signal Kind"
                      hint="Filter by a single dementia-signal kind. Leave empty to include all kinds."
                      persistent-hint
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      rounded="lg"
                      clearable
                      class="mb-4"
                    />

                    <v-row>
                      <v-col cols="12" md="6">
                        <v-select
                          v-model="cfg.signal_severity_min"
                          :items="severityItems"
                          item-title="label"
                          item-value="value"
                          label="Minimum Severity"
                          variant="outlined"
                          density="compact"
                          hide-details="auto"
                          rounded="lg"
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-text-field
                          v-model.number="cfg.signal_window_minutes"
                          label="Lookback (minutes)"
                          type="number"
                          :min="1"
                          :max="1440"
                          :rules="[v => (Number.isInteger(Number(v)) && v >= 1 && v <= 1440) || 'Must be 1..1440']"
                          variant="outlined"
                          density="compact"
                          hide-details="auto"
                          rounded="lg"
                        />
                      </v-col>
                    </v-row>

                    <v-text-field
                      v-model="cfg.output_key"
                      label="Output Key"
                      :rules="[v => /^[a-z][a-z0-9_]*$/.test(v) || 'Lowercase letters, digits, underscores only; must start with a letter.']"
                      hint="pipeline_data key for the result dict. Default: presence."
                      persistent-hint
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      rounded="lg"
                      class="mt-4"
                    />

                    <v-alert type="info" variant="tonal" density="compact" class="mt-4">
                      This step also writes flat keys at the top of pipeline_data: <code>presence_status</code>, <code>presence_room_name</code>, <code>presence_dwell_minutes</code>, <code>presence_at_home</code>, <code>presence_asleep</code>, <code>presence_away</code>. Use these directly in <code>condition</code> step expressions.
                    </v-alert>
                  </v-form>
                </template>

                <!-- home_state -->
                <template v-if="localStep.step_type === 'home_state'">
                  <v-form ref="homeStateForm" v-model="homeStateValid">
                    <v-combobox
                      v-model="cfg.person_id"
                      :items="availablePersons"
                      label="Person"
                      hint="Person whose home-state to derive. Supports {{template}} syntax."
                      persistent-hint
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      rounded="lg"
                      clearable
                      class="mb-4"
                    />

                    <v-text-field
                      v-model="cfg.output_key"
                      label="Output Key"
                      :rules="[v => /^[a-z][a-z0-9_]*$/.test(v) || 'Lowercase letters, digits, underscores only; must start with a letter.']"
                      hint="pipeline_data key prefix. Emits <key>_at_home, <key>_asleep, <key>_away, <key>_state_unknown. Default: home."
                      persistent-hint
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      rounded="lg"
                    />
                  </v-form>
                </template>

                <!-- daily_report -->
                <template v-if="localStep.step_type === 'daily_report'">
                  <v-combobox
                    v-model="cfg.person_ids"
                    :items="availablePersons"
                    label="Person IDs"
                    multiple
                    chips
                    closable-chips
                    hint="Leave empty to generate reports for all active household members."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model.number="cfg.report_date_offset_days"
                    label="Report Date Offset (days)"
                    type="number"
                    hint="0 = today, -1 = yesterday."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-checkbox v-model="cfg.generate_summary_text" label="Generate LLM prose summary" hide-details class="mb-3" />
                  <v-text-field
                    v-if="cfg.generate_summary_text"
                    v-model="cfg.summary_model_id"
                    label="Summary Model ID"
                    hint="LLM model ID for summary generation."
                    persistent-hint
                    class="mb-4"
                  />
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the report list. Default: daily_reports"
                    persistent-hint
                  />
                </template>

                <!-- interactive_prompt -->
                <template v-if="localStep.step_type === 'interactive_prompt'">
                  <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                    Configure at least one channel (popup or voice) to prompt the user for a response.
                  </v-alert>

                  <v-textarea
                    v-model="cfg.popup_message_template"
                    label="Popup Message Template"
                    rows="3"
                    hint="Message shown in the PWA popup dialog. Use {{variable}} syntax for pipeline data."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-row>
                    <v-col cols="12" md="6">
                      <v-text-field
                        v-model="cfg.popup_title"
                        label="Popup Title"
                        hint="Default: 'Question for You'"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="12" md="6">
                      <v-select
                        v-model="cfg.popup_icon"
                        :items="interactivePromptIconOptions"
                        item-title="title"
                        item-value="value"
                        label="Popup Icon"
                        hint="Icon displayed at the top of the popup"
                        persistent-hint
                      >
                        <template v-slot:item="{ props: itemProps, item }">
                          <v-list-item v-bind="itemProps">
                            <template v-slot:prepend>
                              <v-icon>{{ item.raw.value }}</v-icon>
                            </template>
                          </v-list-item>
                        </template>
                        <template v-slot:selection="{ item }">
                          <v-icon class="mr-2">{{ item.raw.value }}</v-icon>
                          {{ item.raw.title }}
                        </template>
                      </v-select>
                    </v-col>
                  </v-row>

                  <v-textarea
                    v-model="cfg.voice_prompt_template"
                    label="Voice Prompt Template"
                    rows="3"
                    hint="Conversational prompt for Gemini Live voice channel. Use {{variable}} syntax. When set, the microphone auto-enables so the user can reply."
                    persistent-hint
                    class="mb-4"
                  />

                  <v-divider class="mb-4" />
                  
                  <v-row>
                    <v-col cols="6">
                      <v-text-field
                        v-model="cfg.escalate_button_text"
                        label="Escalate Button Text"
                        hint="Default: 'I need help'"
                        persistent-hint
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field
                        v-model="cfg.dismiss_button_text"
                        label="Dismiss Button Text"
                        hint="Default: 'I'm okay'"
                        persistent-hint
                      />
                    </v-col>
                  </v-row>
                  
                  <v-slider
                    v-model="cfg.countdown_seconds"
                    label="Countdown Duration (seconds)"
                    :min="5"
                    :max="300"
                    :step="5"
                    thumb-label="always"
                    color="primary"
                    class="mb-4"
                  />
                  
                  <v-select
                    v-model="cfg.timeout_action"
                    :items="[
                      { title: 'Escalate (treat as help needed)', value: 'escalate' },
                      { title: 'Dismiss (treat as okay)', value: 'dismiss' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="Timeout Action"
                    hint="Action to take when user doesn't respond in time"
                    persistent-hint
                    class="mb-4"
                  />
                  
                  <v-checkbox
                    v-model="cfg.auto_escalate"
                    label="Auto-escalate on affirmative response or timeout"
                    hint="Sets pipeline_data.auto_escalate_triggered flag for downstream conditional logic"
                    persistent-hint
                    class="mb-4"
                  />
                  
                  <v-text-field
                    v-model="cfg.output_key"
                    label="Output Key"
                    hint="pipeline_data key for the response. Default: interactive_response"
                    persistent-hint
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

              <!-- Images tab (llm_call) -->
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
                      { title: 'Selected cameras', value: 'additional' },
                      { title: 'Trigger + selected cameras', value: 'both' },
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

                  <template v-if="cfg.image_source === 'trigger' || cfg.image_source === 'both'">
                    <v-card variant="tonal" class="mb-4 pa-4">
                      <div class="text-subtitle-2">Trigger Camera</div>
                      <v-text-field
                        v-model.number="cfg.trigger_images_count"
                        label="Max frames"
                        type="number"
                        :min="0"
                        hint="0 = include all available trigger frames"
                        persistent-hint
                        density="compact"
                        class="mt-2"
                      />
                    </v-card>
                  </template>

                  <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
                    <div class="text-subtitle-2 mb-2">Additional Cameras</div>
                    <v-text-field
                      v-model.number="cfg.images_per_sensor"
                      label="Default frames per camera"
                      type="number"
                      :min="1"
                      hint="Per-camera default; individual cameras can override below"
                      persistent-hint
                      density="compact"
                      class="mb-4"
                    />

                    <v-data-table
                      :headers="[{ title: 'Camera Sensor', key: 'sensor_id' }, { title: 'Frames', key: 'frames', width: 120 }, { title: '', key: 'actions', width: 60, sortable: false }]"
                      :items="cameraRows"
                      item-key="sensor_id"
                      show-select
                      hide-default-footer
                      class="mb-4"
                    >
                      <template v-slot:item.frames="{ item }">
                        <v-text-field
                          :model-value="item.frames"
                          type="number"
                          :min="1"
                          density="compact"
                          hide-details
                          class="v-text-field--flush-label"
                          :class="item.isOverride ? '' : 'text-grey'"
                          @update:model-value="updateSensorFrameLimit(item.sensor_id, Number($event))"
                        />
                      </template>
                      <template v-slot:item.actions="{ item }">
                        <v-btn icon size="x-small" variant="text" @click="removeCamera(item.sensor_id)">
                          <v-icon>mdi-close</v-icon>
                        </v-btn>
                      </template>
                    </v-data-table>

                    <v-combobox
                      v-model="newCameraId"
                      :items="cameraSensorItems.filter(id => !cfg.additional_sensor_ids.includes(id))"
                      label="Add Camera"
                      clearable
                      hide-details
                      class="mb-4"
                      @update:model-value="addCamera"
                    />

                    <v-checkbox
                      v-model="showAdditionalRooms"
                      label="Pull from rooms (all cameras in these rooms)"
                      hide-details
                      class="mb-2"
                    />
                    <v-combobox
                      v-if="showAdditionalRooms"
                      v-model="cfg.additional_room_names"
                      :items="availableRooms"
                      label="Rooms"
                      multiple
                      chips
                      closable-chips
                      hide-details
                      class="mb-4"
                    />
                  </template>

                  <v-card variant="tonal" class="mb-4 pa-4">
                    <v-checkbox
                      v-model="cfg.sort_by_sensor_then_time"
                      label="Group by sensor, then chronological within each sensor"
                      hide-details
                    />
                    <div class="text-caption text-medium-emphasis ml-8 mt-1">
                      Enables inter-frame temporal analysis. Images are ordered:
                      all frames from sensor 1 (oldest to newest), then sensor 2, etc.
                    </div>
                  </v-card>

                  <v-checkbox
                    v-model="cfg.use_annotated_image"
                    label="Use annotated image (from person identification)"
                    hide-details
                    class="mb-4"
                  />

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


                <template v-else-if="localStep.step_type === 'scene_analysis'">
                  <v-select
                    v-model="cfg.image_source"
                    :items="[
                      { title: 'Trigger frames', value: 'trigger' },
                      { title: 'Selected cameras', value: 'additional' },
                      { title: 'Trigger + selected cameras', value: 'both' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="Image Source"
                    class="mb-4"
                  />

                  <v-text-field
                    v-model.number="cfg.max_images"
                    label="Max Images (total)"
                    type="number"
                    :min="1"
                    hint="Hard cap on total images analysed"
                    persistent-hint
                    class="mb-4"
                  />

                  <template v-if="cfg.image_source === 'trigger' || cfg.image_source === 'both'">
                    <v-card variant="tonal" class="mb-4 pa-4">
                      <div class="text-subtitle-2">Trigger Camera</div>
                      <v-text-field
                        v-model.number="cfg.trigger_images_count"
                        label="Max frames"
                        type="number"
                        :min="0"
                        hint="0 = include all available trigger frames"
                        persistent-hint
                        density="compact"
                        class="mt-2"
                      />
                    </v-card>
                  </template>

                  <template v-if="cfg.image_source === 'additional' || cfg.image_source === 'both'">
                    <div class="text-subtitle-2 mb-2">Additional Cameras</div>
                    <v-text-field
                      v-model.number="cfg.images_per_sensor"
                      label="Default frames per camera"
                      type="number"
                      :min="1"
                      hint="Per-camera default; individual cameras can override below"
                      persistent-hint
                      density="compact"
                      class="mb-4"
                    />

                    <v-data-table
                      :headers="[{ title: 'Camera Sensor', key: 'sensor_id' }, { title: 'Frames', key: 'frames', width: 120 }, { title: '', key: 'actions', width: 60, sortable: false }]"
                      :items="cameraRows"
                      item-key="sensor_id"
                      show-select
                      hide-default-footer
                      class="mb-4"
                    >
                      <template v-slot:item.frames="{ item }">
                        <v-text-field
                          :model-value="item.frames"
                          type="number"
                          :min="1"
                          density="compact"
                          hide-details
                          class="v-text-field--flush-label"
                          :class="item.isOverride ? '' : 'text-grey'"
                          @update:model-value="updateSensorFrameLimit(item.sensor_id, Number($event))"
                        />
                      </template>
                      <template v-slot:item.actions="{ item }">
                        <v-btn icon size="x-small" variant="text" @click="removeCamera(item.sensor_id)">
                          <v-icon>mdi-close</v-icon>
                        </v-btn>
                      </template>
                    </v-data-table>

                    <v-combobox
                      v-model="newCameraId"
                      :items="cameraSensorItems.filter(id => !(cfg.additional_sensor_ids || []).includes(id))"
                      label="Add Camera"
                      clearable
                      hide-details
                      class="mb-4"
                      @update:model-value="addCamera"
                    />

                    <v-checkbox
                      v-model="showAdditionalRooms"
                      label="Pull from rooms (all cameras in these rooms)"
                      hide-details
                      class="mb-2"
                    />
                    <v-combobox
                      v-if="showAdditionalRooms"
                      v-model="cfg.additional_room_names"
                      :items="availableRooms"
                      label="Rooms"
                      multiple
                      chips
                      closable-chips
                      hide-details
                      class="mb-4"
                    />
                  </template>

                  <v-card variant="outlined" class="pa-4">
                    <div class="text-subtitle-2 mb-3">
                      <v-icon size="small" class="mr-1">mdi-clock-outline</v-icon>
                      Time Filter (optional)
                    </div>
                    <v-text-field
                      v-model.number="sceneImageTimeFilter.since_minutes"
                      label="Since (minutes ago)"
                      type="number"
                      :min="0"
                      class="mb-3"
                    />
                    <v-row>
                      <v-col cols="6">
                        <v-text-field v-model="sceneImageTimeFilter.time_start" label="Time Start" placeholder="08:00" />
                      </v-col>
                      <v-col cols="6">
                        <v-text-field v-model="sceneImageTimeFilter.time_end" label="Time End" placeholder="18:00" />
                      </v-col>
                    </v-row>
                  </v-card>
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
                    hint="Pipeline data key for the result. Use 'logic_response' or 'translation' for downstream step compatibility."
                    persistent-hint
                  />
                </template>

              </v-window-item>

              <!-- Notification: templates tab -->
              <v-window-item value="templates">
                <template v-if="localStep.step_type === 'notification'">
                  <v-textarea
                    v-model="cfg.message_template"
                    label="Default Message Template"
                    rows="3"
                    hint="Default for all channels. Use {{message}}, {{room_name}}, {{vision_response}}, {{logic_response.user_notification}}, etc."
                    persistent-hint
                    class="mb-5"
                  />
                  <div class="text-overline text-medium-emphasis mb-2">Per-Channel Overrides</div>
                  <v-textarea
                    v-model="cfg.telegram_template"
                    label="Telegram Template"
                    rows="3"
                    hint="HTML supported. Use {{message}}, {{room_name}}, etc. Falls back to the default template."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.eink_template"
                    label="E-Ink Template"
                    rows="2"
                    hint="Short plain-text for e-ink displays. Use {{message}}, {{room_name}}, etc."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.ha_speaker_tts_template"
                    label="HA Speaker TTS / PWA Announcement Template"
                    rows="2"
                    hint="Natural language for spoken announcements. Use {{message}}, {{room_name}}, etc."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.pwa_popup_text_template"
                    label="PWA Popup Text Template"
                    rows="2"
                    hint="Notification text shown in the companion UI overlay. Use {{message}}, {{room_name}}, etc."
                    persistent-hint
                    class="mb-3"
                  />
                  <v-textarea
                    v-model="cfg.pwa_realtime_ai_template"
                    label="PWA Realtime AI Template"
                    rows="2"
                    hint="Conversational voice prompt for Gemini Live delivery. Use {{message}}, {{room_name}}, etc."
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
                      hint="JSON payload template. Use {{message}}, {{room_name}}, etc. Falls back to a basic JSON envelope."
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

              <!-- Advanced tab (llm_call sampling) -->
              <v-window-item value="advanced">

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
          <div class="step-config-vars px-4 py-5 d-none d-md-flex flex-column" style="position: relative;">
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
            <Transition name="copied-fade">
              <div v-if="copiedToken" class="copied-toast">
                <v-icon size="14" color="success" class="mr-1">mdi-check</v-icon>
                <span class="text-caption">Copied <code>{{ copiedToken }}</code></span>
              </div>
            </Transition>
          </div>
        </div>
      </div>

      <v-divider />

      <v-card-actions class="px-6 py-3">
        <v-icon size="small" color="medium-emphasis" class="mr-1">mdi-information-outline</v-icon>
        <span class="text-caption text-medium-emphasis">
          Use <code class="cc-code">&#123;&#123;key&#125;&#125;</code> in prompts and templates to reference pipeline variables. Labeled steps are also accessible as <code class="cc-code">&#123;&#123;step_label.key&#125;&#125;</code>.
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
  allSteps: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue", "save"]);

const knownTypes = [
  "llm_call",
  "person_identification",
  "scene_analysis",
  "object_trend_analysis",
  "notification",
  "ha_action",
  "activity_detection",
  "activity_session_start",
  "activity_session_end",
  "daily_report",
  "wait",
  "condition",
  "verification",
  "interactive_prompt",
  "presence_query",
  "home_state",
];

const STEP_ICONS = {
  person_identification: "mdi-face-recognition",
  scene_analysis: "mdi-image-search",
  object_trend_analysis: "mdi-chart-line",
  llm_call: "mdi-brain",
  notification: "mdi-bell-outline",
  ha_action: "mdi-home-automation",
  activity_detection: "mdi-run",
  activity_session_start: "mdi-play",
  activity_session_end: "mdi-stop",
  daily_report: "mdi-file-chart",
  wait: "mdi-timer-sand",
  condition: "mdi-help-circle-outline",
  verification: "mdi-check-decagram-outline",
  interactive_prompt: "mdi-message-question",
  semantic_memory_write: "mdi-database-plus-outline",
  semantic_memory_query: "mdi-database-search-outline",
  presence_query: "mdi-map-marker-radius",
  home_state: "mdi-home-variant",
};

const stepIcon = computed(() => STEP_ICONS[localStep.step_type] || "mdi-cog-outline");

const LABEL_RE = /^[a-z][a-z0-9_]*$/;
const labelRules = [
  (v) => !!v || "Step label is required",
  (v) => LABEL_RE.test(v) || "Label must start with a letter and contain only lowercase letters, digits, and underscores",
];
const labelUniqueError = computed(() => {
  const label = localStep.label;
  if (!label) return "";
  const currentId = props.step?.id;
  const conflict = props.allSteps.find((s) => s.label === label && s.id !== currentId);
  return conflict ? `Label '${label}' is already used by another step in this pipeline` : "";
});

const interactivePromptIconOptions = [
  { title: "Question", value: "mdi-message-question" },
  { title: "Help", value: "mdi-help-circle" },
  { title: "Warning", value: "mdi-alert" },
  { title: "Alert", value: "mdi-alert-circle" },
  { title: "Critical Alert", value: "mdi-alert-octagon" },
  { title: "Bell", value: "mdi-bell" },
  { title: "Bell Ring", value: "mdi-bell-ring" },
  { title: "Information", value: "mdi-information" },
  { title: "Speaker", value: "mdi-volume-high" },
  { title: "Voice", value: "mdi-account-voice" },
  { title: "Check", value: "mdi-check-circle" },
  { title: "Health", value: "mdi-heart-pulse" },
  { title: "Medication", value: "mdi-pill" },
  { title: "Greeting", value: "mdi-human-greeting" },
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
  "scene_memory_observation_id",
  "semantic_memory_observation_id",
  "semantic_memory_movement_ids",
  "memory_context",
];

const conditionExamples = [
  {
    label: "LLM flagged an alert",
    description: "True when an llm_call step set is_notification_needed to true.",
    expr: "steps.llm_call_1.outputs.llm_response.is_notification_needed == true",
  },
  {
    label: "LLM response severity is high",
    description: "Case-sensitive string comparison on a nested field.",
    expr: 'steps.llm_call_1.outputs.llm_response.alert_level == "emergency"',
  },
  {
    label: "Scene description mentions a keyword",
    description: "icontains() checks case-insensitively — no need for lower().",
    expr: 'icontains(steps.scene_analysis_1.outputs.scene_description, "kitchen")',
  },
  {
    label: "Any detection with a specific label",
    description: "jq() + JMESPath filter; icontains() inside the filter handles mixed case.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") > 0",
  },
  {
    label: "High-confidence detection of a specific object",
    description: "Backtick-quoted numbers are JMESPath JSON literals for numeric comparisons.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?label == 'person' && confidence > `0.9`])\") > 0",
  },
  {
    label: "Any medium or higher hazard present",
    description: "Filter the hazards list by severity field.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_hazards[?severity == 'medium' || severity == 'high'])\") > 0",
  },
  {
    label: "Exact detection count",
    description: "Compare the count of matching detections to a specific number.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") == 2",
  },
  {
    label: "Person detected AND scene keyword match",
    description: "Combine a jq() filter with an icontains() check using and.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") > 0 and icontains(steps.scene_analysis_1.outputs.scene_description, \"kitchen\")",
  },
  {
    label: "Person detected AND scene keyword match",
    description: "Combine a jq() filter with an icontains() check using and.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_detections[?icontains(label, 'person')])\") > 0 and icontains(steps.scene_analysis_1.outputs.scene_description, \"kitchen\")",
  },
  {
    label: "Per-image: first image describes a specific room",
    description: "Access the description of a single image by index inside scene_images[].",
    expr: "jq(\"contains(lower(steps.scene_analysis_1.outputs.scene_images[0].scene_description), 'kitchen')\")",
  },
  {
    label: "Per-image: any image has a specific detection",
    description: "[] flattens detections across all images; pipe | applies the filter on the flat list.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_images[].scene_detections[] | [?label == 'person'])\") > 0",
  },
  {
    label: "Per-image: second image has hazards",
    description: "Check the hazard list on a specific image by index.",
    expr: "jq(\"length(steps.scene_analysis_1.outputs.scene_images[1].scene_hazards)\") > 0",
  },
  {
    label: "Interactive prompt escalated",
    description: "Check what the user chose in an interactive_prompt step.",
    expr: 'steps.interactive_prompt_1.outputs.interactive_response.action == "escalate"',
  },
  {
    label: "Step output key exists",
    description: "exists() returns false if the path is missing or null.",
    expr: "exists(steps.scene_analysis_1.outputs.scene_description)",
  },
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
const sceneImageTimeFilter = reactive({ since_minutes: null, time_start: "", time_end: "" });
const llmJsonSchemaError = ref("");
const cameraSensorItems = ref([]);

// presence_query form refs and constants
const presenceQueryValid = ref(true);
const presenceQueryForm = ref(null);
const homeStateValid = ref(true);
const homeStateForm = ref(null);
const knownSignalKinds = [
  "bathroom_dwell_anomaly",
  "pacing",
  "nighttime_movement",
  "stillness_anomaly",
  "absence",
  "sundowning_index",
];
const severityItems = [
  { label: "Info", value: "info" },
  { label: "Warning", value: "warning" },
  { label: "Emergency", value: "emergency" },
];

const activeTab = ref("general");
const varSearch = ref("");
const copiedToken = ref("");

// LLM model registry (for the llm_call step)
const llmModelItems = ref([]);
const selectedLLMModel = computed(() =>
  llmModelItems.value.find((m) => m.id === cfg.model_id) || null
);

// llm_call camera table state
const newCameraId = ref(null);
const showAdditionalRooms = ref(false);

const cameraRows = computed(() => {
  const sensors = cfg.additional_sensor_ids || [];
  const limits = cfg.sensor_frame_limits || {};
  const defaultLimit = cfg.images_per_sensor || 3;
  return sensors.map(id => ({
    sensor_id: id,
    frames: limits[id] ?? defaultLimit,
    isOverride: id in limits,
  }));
});

function updateSensorFrameLimit(sensorId, value) {
  const defaultLimit = cfg.images_per_sensor || 3;
  if (!cfg.sensor_frame_limits) cfg.sensor_frame_limits = {};
  if (value <= 0 || value === defaultLimit) {
    delete cfg.sensor_frame_limits[sensorId];
  } else {
    cfg.sensor_frame_limits[sensorId] = value;
  }
}

function addCamera() {
  if (!newCameraId.value) return;
  if (!cfg.additional_sensor_ids) cfg.additional_sensor_ids = [];
  if (!cfg.additional_sensor_ids.includes(newCameraId.value)) {
    cfg.additional_sensor_ids.push(newCameraId.value);
  }
  newCameraId.value = null;
}

function removeCamera(sensorId) {
  cfg.additional_sensor_ids = (cfg.additional_sensor_ids || []).filter(
    id => id !== sensorId
  );
  if (cfg.sensor_frame_limits) {
    delete cfg.sensor_frame_limits[sensorId];
  }
}

// Pipeline data reference for the always-visible sidebar.
// Grouped by step type. Keys match exactly what each step writes to pipeline_data.
const pipelineDataReference = [
  // -- Trigger context -------------------------------------------------------
  { key: "trigger.sensor_id",           source: "Trigger context" },
  { key: "trigger.room_name",           source: "Trigger context" },
  { key: "trigger.media_paths",         source: "Trigger context" },
  { key: "trigger_input",               source: "Webhook / Telegram payload" },
  { key: "trigger_input.command",       source: "Telegram trigger" },
  { key: "trigger_input.chat_id",       source: "Telegram trigger" },
  { key: "trigger_input.args",          source: "Telegram trigger (list)" },
  { key: "trigger_input.text",          source: "Telegram / webhook raw text" },
  // -- Path pattern ----------------------------------------------------------
  { key: "steps.<label>.outputs.<key>", source: "General pattern — replace <label> with the step label" },
  // -- person_identification -------------------------------------------------
  { key: "steps.person_identification_1.outputs.person_detections",                     source: "person_identification" },
  { key: "steps.person_identification_1.outputs.person_detections.0.person_id",         source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.person_detections.0.name",              source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.person_detections.0.confidence",        source: "person_identification: first match" },
  { key: "steps.person_identification_1.outputs.person_detections.0.bbox",              source: "person_identification: [x1,y1,x2,y2] pixels" },
  { key: "steps.person_identification_1.outputs.person_detections.0.direction",         source: "person_identification: motion direction" },
  { key: "steps.person_identification_1.outputs.person_detections.0.source_media_path", source: "person_identification: presigned URL of frame" },
  { key: "steps.person_identification_1.outputs.room_transitions",                      source: "person_identification" },
  { key: "steps.person_identification_1.outputs.annotated_image",                       source: "person_identification: base64 bbox overlay" },
  // -- scene_analysis --------------------------------------------------------
  { key: "steps.scene_analysis_1.outputs.scene_detections",             source: "scene_analysis: YOLO object list" },
  { key: "steps.scene_analysis_1.outputs.scene_detections.0.label",    source: "scene_analysis: object label" },
  { key: "steps.scene_analysis_1.outputs.scene_detections.0.confidence", source: "scene_analysis: detection confidence" },
  { key: "steps.scene_analysis_1.outputs.scene_detections.0.bbox",     source: "scene_analysis: [x1,y1,x2,y2]" },
  { key: "steps.scene_analysis_1.outputs.scene_description",           source: "scene_analysis: Florence-2 text" },
  { key: "steps.scene_analysis_1.outputs.scene_hazards",               source: "scene_analysis: hazard alert list" },
  { key: "steps.scene_analysis_1.outputs.scene_hazards.0.name",        source: "scene_analysis: hazard name" },
  { key: "steps.scene_analysis_1.outputs.scene_hazards.0.severity",    source: "scene_analysis: ok/warning/critical" },
  { key: "steps.scene_analysis_1.outputs.scene_hazards.0.description", source: "scene_analysis: hazard description" },
  // -- object_trend_analysis -------------------------------------------------
  { key: "steps.object_trend_analysis_1.outputs.room_trends",             source: "object_trend_analysis: map of room to trend" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends_any_warning", source: "object_trend_analysis: bool" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends_max_severity", source: "object_trend_analysis: ok/info/warning/critical" },
  { key: "steps.object_trend_analysis_1.outputs.room_trends_summary",     source: "object_trend_analysis: compact text for LLM" },
  // -- llm_call --------------------------------------------------------------
  { key: "steps.llm_call_1.outputs.llm_response",                        source: "llm_call (default output_key)" },
  { key: "steps.llm_call_1.outputs.llm_response.is_notification_needed", source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.user_notification",      source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.alert_level",            source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.reasoning",              source: "llm_call: default notification schema" },
  { key: "steps.llm_call_1.outputs.llm_response.activities",             source: "llm_call: activity detection schema" },
  // -- activity_detection ----------------------------------------------------
  { key: "steps.activity_detection_1.outputs.detected_activities",                   source: "activity_detection" },
  { key: "steps.activity_detection_1.outputs.detected_activities.0.person_id",       source: "activity_detection: first entry" },
  { key: "steps.activity_detection_1.outputs.detected_activities.0.activity_type",   source: "activity_detection: first entry" },
  { key: "steps.activity_detection_1.outputs.detected_activities.0.room_name",       source: "activity_detection: first entry" },
  { key: "steps.activity_detection_1.outputs.detected_activities.0.confidence",      source: "activity_detection: first entry" },
  // -- activity_session_start ------------------------------------------------
  { key: "steps.activity_session_start_1.outputs.session",              source: "activity_session_start (default output_key)" },
  { key: "steps.activity_session_start_1.outputs.session.session_id",   source: "activity_session_start" },
  { key: "steps.activity_session_start_1.outputs.session.person_id",    source: "activity_session_start" },
  { key: "steps.activity_session_start_1.outputs.session.activity_type", source: "activity_session_start" },
  { key: "steps.activity_session_start_1.outputs.session.room_name",    source: "activity_session_start" },
  { key: "steps.activity_session_start_1.outputs.session.started_at",   source: "activity_session_start: ISO timestamp" },
  { key: "steps.activity_session_start_1.outputs.session.was_existing", source: "activity_session_start: bool, true if reused" },
  // -- activity_session_end --------------------------------------------------
  { key: "steps.activity_session_end_1.outputs.closed_session",                  source: "activity_session_end (default output_key)" },
  { key: "steps.activity_session_end_1.outputs.closed_session.session_id",       source: "activity_session_end" },
  { key: "steps.activity_session_end_1.outputs.closed_session.duration_minutes", source: "activity_session_end" },
  { key: "steps.activity_session_end_1.outputs.closed_session.closed_at",        source: "activity_session_end: ISO timestamp" },
  { key: "steps.activity_session_end_1.outputs.closed_session.closed_via",       source: "activity_session_end: explicit/timeout/stale" },
  { key: "steps.activity_session_end_1.outputs.closed_session.status",           source: "activity_session_end" },
  // -- verification ----------------------------------------------------------
  { key: "steps.verification_1.outputs.verification.verified",             source: "verification: bool" },
  { key: "steps.verification_1.outputs.verification.match_mode",           source: "verification: all/any" },
  { key: "steps.verification_1.outputs.verification.matched_conditions",   source: "verification: list" },
  { key: "steps.verification_1.outputs.verification.unmatched_conditions", source: "verification: list" },
  // -- condition -------------------------------------------------------------
  { key: "steps.condition_1.outputs.condition.result",   source: "condition: bool" },
  { key: "steps.condition_1.outputs.condition.expression", source: "condition" },
  { key: "steps.condition_1.outputs.condition.branch",   source: "condition: true/false" },
  // -- ha_action -------------------------------------------------------------
  { key: "steps.ha_action_1.outputs.ha_action.success",   source: "ha_action: bool" },
  { key: "steps.ha_action_1.outputs.ha_action.domain",    source: "ha_action" },
  { key: "steps.ha_action_1.outputs.ha_action.service",   source: "ha_action" },
  { key: "steps.ha_action_1.outputs.ha_action.entity_id", source: "ha_action" },
  // -- notification ----------------------------------------------------------
  { key: "steps.notification_1.outputs.notification_dispatched", source: "notification: bool" },
  { key: "steps.notification_1.outputs.notification_channels",   source: "notification: map of channel to result" },
  // -- daily_report ----------------------------------------------------------
  { key: "steps.daily_report_1.outputs.daily_reports",                  source: "daily_report (default output_key)" },
  { key: "steps.daily_report_1.outputs.daily_reports.0.person_id",      source: "daily_report: first entry" },
  { key: "steps.daily_report_1.outputs.daily_reports.0.report_date",    source: "daily_report: YYYY-MM-DD" },
  { key: "steps.daily_report_1.outputs.daily_reports.0.wellness_score", source: "daily_report: 0-100" },
  // -- semantic_memory_write -------------------------------------------------
  { key: "steps.semantic_memory_write_1.outputs.semantic_memory_observation_id", source: "semantic_memory_write: stored observation ID" },
  { key: "steps.semantic_memory_write_1.outputs.semantic_memory_movement_ids",   source: "semantic_memory_write: list of movement IDs" },
  // -- semantic_memory_query -------------------------------------------------
  { key: "steps.semantic_memory_query_1.outputs.memory_context.summary",             source: "semantic_memory_query: LLM-ready summary" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.recent_objects",      source: "semantic_memory_query: object label list" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.recent_hazards",      source: "semantic_memory_query: hazard list" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.observations",        source: "semantic_memory_query: observation records" },
  { key: "steps.semantic_memory_query_1.outputs.memory_context.observations_count",  source: "semantic_memory_query: int" },
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
  } else if (t === "scene_analysis") {
    all.push({ key: "images", label: "Images", icon: "mdi-camera-outline" });
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
    trigger_images_count: 0,
    additional_sensor_ids: [],
    additional_room_names: [],
    images_per_sensor: 3,
    sensor_frame_limits: {},
    sort_by_sensor_then_time: false,
    use_annotated_image: false,
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
  scene_analysis: {
    run_detect: true,
    run_describe: true,
    run_embed: false,
    run_hazards: true,
    write_to_memory: false,
    image_source: "trigger",
    max_images: 1,
    trigger_images_count: 0,
    additional_sensor_ids: [],
    additional_room_names: [],
    images_per_sensor: 1,
    sensor_frame_limits: {},
    image_time_filter: {},
  },
  object_trend_analysis: {
    room_ids: [],
    include_snapshots_hours: 0,
    severity_threshold: "info",
    output_key: "room_trends",
  },
  activity_session_start: {
    activity_type: "",
    person_id: "",
    room_name: "",
    confidence: 0.85,
    timeout_minutes: "",
    metadata_extra: "",
    output_key: "session",
  },
  activity_session_end: {
    activity_type: "",
    person_id: "",
    write_activity_record: true,
    output_key: "closed_session",
  },
  daily_report: {
    person_ids: [],
    report_date_offset_days: 0,
    generate_summary_text: false,
    summary_model_id: "",
    notify_on_complete: false,
    output_key: "daily_reports",
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

    // Reset llm_call UI state
    showAdditionalRooms.value = false;

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

    // Populate sceneImageTimeFilter for scene_analysis
    if (step.step_type === "scene_analysis") {
      const tf = incoming.image_time_filter || {};
      sceneImageTimeFilter.since_minutes = tf.since_minutes || null;
      sceneImageTimeFilter.time_start = tf.time_start || "";
      sceneImageTimeFilter.time_end = tf.time_end || "";
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
  activity_session_start: "Start Activity Session",
  activity_session_end: "End Activity Session",
  daily_report: "Generate Daily Report",
  object_trend_analysis: "Room Trend Query",
  scene_analysis: "Scene Analysis",
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
  // Validate presence_query form
  if (localStep.step_type === "presence_query") {
    presenceQueryForm.value?.validate();
    if (!presenceQueryValid.value) {
      notify("Fix validation errors before saving.", "error");
      return;
    }
  }
  // Validate home_state form
  if (localStep.step_type === "home_state") {
    homeStateForm.value?.validate();
    if (!homeStateValid.value) {
      notify("Fix validation errors before saving.", "error");
      return;
    }
  }

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

    // Merge sceneImageTimeFilter into scene_analysis config
    if (localStep.step_type === "scene_analysis") {
      const tf = {};
      if (sceneImageTimeFilter.since_minutes) tf.since_minutes = sceneImageTimeFilter.since_minutes;
      if (sceneImageTimeFilter.time_start) tf.time_start = sceneImageTimeFilter.time_start;
      if (sceneImageTimeFilter.time_end) tf.time_end = sceneImageTimeFilter.time_end;
      config.image_time_filter = Object.keys(tf).length > 0 ? tf : {};
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
  overflow-x: hidden;
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
  flex-shrink: 0;
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

.copied-toast {
  position: absolute;
  bottom: 16px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  background: rgba(var(--v-theme-success), 0.12);
  border: 1px solid rgba(var(--v-theme-success), 0.3);
  border-radius: 8px;
  padding: 6px 10px;
  pointer-events: none;
}

.copied-fade-enter-active,
.copied-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.copied-fade-enter-from,
.copied-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.condition-expression-textarea :deep(textarea) {
  font-family: var(--cc-font-mono);
  font-size: 13px;
  line-height: 1.6;
}

.condition-examples-list {
  background: transparent;
}

.condition-example-row {
  cursor: pointer;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  transition: background-color 0.12s ease;
}

.condition-example-row:last-child {
  border-bottom: none;
}

.condition-example-row:hover {
  background-color: rgba(10, 132, 255, 0.07);
}

.condition-example-code {
  display: block;
  font-family: var(--cc-font-mono);
  font-size: 11.5px;
  color: var(--cc-brand);
  background: rgba(10, 132, 255, 0.06);
  border-radius: 4px;
  padding: 4px 8px;
  white-space: pre-wrap;
  word-break: break-all;
  margin-top: 2px;
}
</style>
