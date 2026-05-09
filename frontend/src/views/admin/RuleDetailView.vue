<template>
  <div v-if="rule">
    <div class="d-flex align-center mb-5">
      <v-btn icon="mdi-arrow-left" variant="text" to="/admin/rules" />
      <div class="ml-2">
        <div class="text-overline text-medium-emphasis">Rule</div>
        <div class="d-flex align-center">
          <h2 class="text-h4 font-weight-bold tracking-tight">{{ rule.name }}</h2>
          <v-chip :color="rule.enabled ? 'success' : 'grey'" size="small" class="ml-3">
            {{ rule.enabled ? "Active" : "Disabled" }}
          </v-chip>
        </div>
      </div>
      <v-spacer />
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-play"
        :loading="executing"
        @click="executeRule"
      >
        Test Run
      </v-btn>
    </div>

    <v-tabs v-model="tab" color="primary" class="mb-2">
      <v-tab value="settings">Settings</v-tab>
      <v-tab value="pipeline">Pipeline</v-tab>
      <v-tab value="contexts">Contexts</v-tab>
      <v-tab value="dependencies">Dependencies</v-tab>
      <v-tab value="executions">Executions</v-tab>
      <v-tab value="liverun" v-if="liveExecutionId">
        <v-icon start :color="livePolling ? 'info' : undefined">
          {{ livePolling ? 'mdi-circle-medium' : 'mdi-flash-outline' }}
        </v-icon>
        Live Run
      </v-tab>
    </v-tabs>

    <v-window v-model="tab" class="mt-4">
      <!-- Settings Tab -->
      <v-window-item value="settings">
        <v-card>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field v-model="form.name" label="Name" variant="outlined" />
              </v-col>
              <v-col cols="12" md="6">
                <v-select
                  v-model="form.trigger_type"
                  :items="triggerTypes"
                  label="Trigger Type"
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12">
                <v-textarea v-model="form.description" label="Description" variant="outlined" rows="2" />
              </v-col>
              <v-col cols="12" md="6">
                <v-autocomplete
                  v-model="form.primary_sensor_id"
                  :items="sensorItems"
                  item-title="_label"
                  item-value="id"
                  label="Primary Sensor"
                  variant="outlined"
                  clearable
                  hint="The sensor that triggers this rule"
                  persistent-hint
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template #prepend>
                        <v-icon size="20" class="mr-2">{{ sensorIcon(item.raw.sensor_type) }}</v-icon>
                      </template>
                      <template #subtitle>
                        {{ item.raw.sensor_type }} · {{ item.raw.room_name || 'No room' }}
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="form.schedule_cron"
                  label="Cron Schedule"
                  variant="outlined"
                  placeholder="*/5 * * * *"
                  :disabled="form.trigger_type !== 'cron'"
                  :hint="form.trigger_type === 'cron' ? `Times are interpreted in ${getAppTimezone()}` : ''"
                  persistent-hint
                />
              </v-col>
              <v-col v-if="form.trigger_type === 'occupancy_duration'" cols="12" md="6">
                <v-text-field
                  v-model.number="form.occupancy_config.min_minutes"
                  label="Occupancy Threshold (min)"
                  type="number"
                  variant="outlined"
                  hint="Fire the rule after the sensor has been occupied this long"
                  persistent-hint
                />
              </v-col>
              <template v-if="form.trigger_type === 'telegram'">
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="form.telegram_trigger_config.command"
                    label="Telegram Command"
                    variant="outlined"
                    placeholder="/medication"
                    hint="Incoming command that fires this rule (e.g. /medication). Leave empty to match any command."
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-combobox
                    v-model="form.telegram_trigger_config.allowed_chat_ids"
                    label="Allowed Chat IDs"
                    variant="outlined"
                    multiple
                    chips
                    closable-chips
                    :hint="
                      form.telegram_trigger_config.allowed_chat_ids?.length
                        ? 'Telegram chat IDs authorised to trigger this rule.'
                        : 'Required: at least one chat ID must be specified.'
                    "
                    persistent-hint
                    :error="!form.telegram_trigger_config.allowed_chat_ids?.length"
                    :rules="[v => (Array.isArray(v) && v.length > 0) || 'At least one chat ID is required']"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-switch
                    v-model="form.telegram_trigger_config.respond_with_ack"
                    label="Send acknowledgment reply"
                    color="primary"
                    hint="Reply to the Telegram message confirming the rule was triggered."
                    persistent-hint
                  />
                </v-col>
              </template>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.cool_off_minutes" label="Cool-off (min)" type="number" variant="outlined" hint="Minimum minutes between executions (0 = no limit)" persistent-hint />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field v-model.number="form.max_daily_triggers" label="Max Daily" type="number" variant="outlined" hint="Maximum executions per day (0 = no limit)" persistent-hint />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field
                  v-model.number="form.max_concurrent_executions"
                  label="Max Concurrent"
                  type="number"
                  variant="outlined"
                  hint="Max simultaneous executions (0 = unlimited)"
                  persistent-hint
                />
              </v-col>
              <v-col cols="6" md="3">
                <v-text-field
                  v-model.number="form.execution_timeout_minutes"
                  label="Timeout (min)"
                  type="number"
                  variant="outlined"
                  hint="Hard time limit per execution (0 = no timeout)"
                  persistent-hint
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-switch v-model="form.enabled" label="Enabled" color="primary" />
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" @click="saveSettings">Save Settings</v-btn>
          </v-card-actions>
        </v-card>
      </v-window-item>

      <!-- Pipeline Tab -->
      <v-window-item value="pipeline">
        <v-card>
          <v-card-text>
            <PipelineBuilder :rule-id="ruleId" @updated="loadRule" />
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- Contexts Tab -->
      <v-window-item value="contexts">
        <v-card>
          <v-card-text>
            <div class="d-flex align-center mb-3">
              <h4 class="text-subtitle-1">Context Filters</h4>
              <v-spacer />
              <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCtxDialog">
                Add Context
              </v-btn>
            </div>
            <v-list v-if="rule.contexts?.length">
              <v-list-item v-for="ctx in rule.contexts" :key="ctx.id">
                <template #prepend>
                  <v-icon size="20" :color="ctxIcon(ctx.context_type).color" class="mr-3">
                    {{ ctxIcon(ctx.context_type).icon }}
                  </v-icon>
                </template>
                <v-list-item-title>
                  <v-chip v-if="ctx.negate" size="small" color="warning" variant="tonal" class="mr-1">NOT</v-chip>
                  <v-chip size="small" color="info" variant="tonal" class="mr-2">{{ ctx.context_type }}</v-chip>
                  {{ ctxSummary(ctx) }}
                </v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteContext(ctx.id)" />
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-grey py-4">No context filters. This rule applies everywhere.</div>
          </v-card-text>
        </v-card>

        <!-- Context Filter Dialog -->
        <v-dialog v-model="ctxDialog" max-width="500">
          <v-card>
            <v-card-title>Add Context Filter</v-card-title>
            <v-card-text>
              <v-select
                v-model="ctxForm.context_type"
                :items="contextTypeItems"
                item-title="label"
                item-value="value"
                label="Context Type"
                variant="outlined"
                class="mb-3"
              />

              <v-switch
                v-model="ctxForm.negate"
                label="Negate (NOT)"
                color="warning"
                hint="Invert the filter: e.g. NOT in this room, NOT during this time"
                persistent-hint
                class="mb-3"
              />

              <!-- Room filter -->
              <template v-if="ctxForm.context_type === 'room'">
                <v-autocomplete
                  v-model="ctxForm.config.room_name"
                  :items="roomNames"
                  label="Room"
                  variant="outlined"
                  hint="Only trigger when the event is in this room"
                  persistent-hint
                />
              </template>

              <!-- Time range filter -->
              <template v-else-if="ctxForm.context_type === 'time_range'">
                <v-text-field
                  v-model="ctxForm.config.start_time"
                  label="Start Time"
                  variant="outlined"
                  type="time"
                  :hint="`Local time in ${getAppTimezone()}`"
                  persistent-hint
                  class="mb-4"
                />
                <v-text-field
                  v-model="ctxForm.config.end_time"
                  label="End Time"
                  variant="outlined"
                  type="time"
                  :hint="`Local time in ${getAppTimezone()}`"
                  persistent-hint
                />
              </template>

              <!-- Day of week filter -->
              <template v-else-if="ctxForm.context_type === 'day_of_week'">
                <v-select
                  v-model="ctxForm.config.days"
                  :items="dayItems"
                  label="Days"
                  variant="outlined"
                  multiple
                  chips
                  closable-chips
                  hint="Only trigger on selected days"
                  persistent-hint
                />
              </template>

              <!-- Person presence filter -->
              <template v-else-if="ctxForm.context_type === 'person_presence'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  clearable
                  class="mb-3"
                />
                <v-select
                  v-model="ctxForm.config.status"
                  :items="['home', 'away', 'unknown']"
                  label="Required Status"
                  variant="outlined"
                  hint="Only trigger when the person has this status"
                  persistent-hint
                  class="mb-3"
                />
                <v-autocomplete
                  v-if="ctxForm.config.status === 'home'"
                  v-model="ctxForm.config.room_name"
                  :items="roomNames"
                  label="In Room (optional)"
                  variant="outlined"
                  clearable
                  hint="Leave empty to match any room while home"
                  persistent-hint
                />
                <v-text-field
                  v-model.number="ctxForm.config.within_minutes"
                  label="Lookback (minutes)"
                  variant="outlined"
                  type="number"
                  hint="How far back to check for presence. Default: 15"
                  persistent-hint
                  class="mb-3"
                />
                <v-checkbox
                  v-model="ctxForm.config.use_semantic_memory"
                  label="Use semantic memory for corroboration"
                  hint="Cross-check with the latest movement record from semantic memory."
                  persistent-hint
                />
              </template>

              <!-- Person activity filter -->
              <template v-else-if="ctxForm.context_type === 'person_activity'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  clearable
                  class="mb-3"
                />
                <v-combobox
                  v-model="ctxForm.config.activity_type"
                  :items="activityTypeItems"
                  label="Activity Type"
                  variant="outlined"
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.within_minutes"
                  label="Within Minutes"
                  variant="outlined"
                  type="number"
                  hint="Check if activity occurred within this time window"
                  persistent-hint
                />
              </template>

              <!-- Home State filter -->
              <template v-else-if="ctxForm.context_type === 'home_state'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  clearable
                  class="mb-3"
                  aria-label="Person whose home-state to evaluate"
                />
                <v-select
                  v-model="ctxForm.config.state"
                  :items="[
                    { title: 'At home (any room or asleep)', value: 'at_home' },
                    { title: 'Asleep (anchored)', value: 'asleep' },
                    { title: 'Away from home', value: 'away' },
                    { title: 'Unknown', value: 'unknown' },
                  ]"
                  item-title="title"
                  item-value="value"
                  label="Required state"
                  :rules="[v => !!v || 'Choose a state.']"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                />
              </template>

              <!-- Presence Status filter -->
              <template v-else-if="ctxForm.context_type === 'presence_status'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  clearable
                  class="mb-3"
                  aria-label="Person whose presence status to evaluate"
                />
                <v-select
                  v-model="ctxForm.config.status"
                  :items="[
                    { title: 'Present in a known room', value: 'present_room' },
                    { title: 'Present at home (room unknown)', value: 'present_home' },
                    { title: 'Asleep', value: 'asleep' },
                    { title: 'Stale', value: 'stale' },
                    { title: 'Away', value: 'away' },
                    { title: 'Unknown', value: 'unknown' },
                  ]"
                  item-title="title"
                  item-value="value"
                  label="Required status"
                  :rules="[v => !!v || 'Choose a status.']"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  class="mb-3"
                />
                <v-autocomplete
                  v-model="ctxForm.config.room_name"
                  :items="roomNames"
                  label="In room (optional)"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  clearable
                  hint="Required only when Status is 'Present in a known room'."
                  persistent-hint
                />
              </template>

              <!-- Presence Dwell filter -->
              <template v-else-if="ctxForm.context_type === 'presence_dwell'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  clearable
                  class="mb-3"
                />
                <v-select
                  v-model="ctxForm.config.status"
                  :items="[
                    { title: 'Any status', value: '' },
                    { title: 'Present in room', value: 'present_room' },
                    { title: 'Asleep', value: 'asleep' },
                  ]"
                  item-title="title"
                  item-value="value"
                  label="With status (optional)"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.min_minutes"
                  label="Minimum dwell (minutes)"
                  type="number"
                  :min="1"
                  :max="1440"
                  :rules="[v => (Number.isInteger(Number(v)) && v >= 1 && v <= 1440) || 'Must be 1..1440.']"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  rounded="lg"
                  hint="Filter triggers only when the person has held the matching status this long."
                  persistent-hint
                />
                <v-alert v-if="ctxForm.config.min_minutes >= 30" type="info" variant="tonal" density="compact" class="mt-2">
                  Long-running filters require a recent presence_query step in the pipeline.
                </v-alert>
              </template>

              <!-- Scene Contains filter -->
              <template v-else-if="ctxForm.context_type === 'scene_contains'">
                <v-combobox
                  v-model="ctxForm.config.objects_any"
                  :items="[]"
                  label="Objects (any)"
                  multiple
                  chips
                  closable-chips
                  hint="Filter observations containing any of these objects"
                  persistent-hint
                  class="mb-3"
                />
                <v-combobox
                  v-model="ctxForm.config.hazard_flags_any"
                  :items="[]"
                  label="Hazard Flags (any)"
                  multiple
                  chips
                  closable-chips
                  hint="Filter observations with any of these hazard flags"
                  persistent-hint
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.within_minutes"
                  label="Lookback (minutes)"
                  variant="outlined"
                  type="number"
                  hint="How far back to check. Default: 60"
                  persistent-hint
                />
              </template>

              <!-- Person Movement (Memory) filter -->
              <template v-else-if="ctxForm.context_type === 'person_movement_memory'">
                <v-autocomplete
                  v-model="ctxForm.config.person_id"
                  :items="personIds"
                  label="Person"
                  variant="outlined"
                  clearable
                  class="mb-3"
                />
                <v-select
                  v-model="ctxForm.config.semantic"
                  :items="['entering', 'exiting', 'approaching_exit', 'entering_depth', 'stationary', 'any']"
                  label="Movement Type"
                  variant="outlined"
                  hint="Direction semantic to match"
                  persistent-hint
                  class="mb-3"
                />
                <v-autocomplete
                  v-model="ctxForm.config.to_room_id"
                  :items="roomNames"
                  label="To Room (optional)"
                  variant="outlined"
                  clearable
                  hint="Filter by destination room"
                  persistent-hint
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.within_minutes"
                  label="Lookback (minutes)"
                  variant="outlined"
                  type="number"
                  hint="How far back to check. Default: 30"
                  persistent-hint
                  class="mb-3"
                />
                <v-text-field
                  v-model.number="ctxForm.config.min_confidence"
                  label="Min Confidence"
                  variant="outlined"
                  type="number"
                  :min="0"
                  :max="1"
                  :step="0.05"
                  hint="Minimum confidence score. Default: 0"
                  persistent-hint
                />
              </template>

              <!-- Fallback: raw JSON -->
              <template v-else>
                <v-textarea
                  v-model="ctxConfigStr"
                  label="Config (JSON)"
                  variant="outlined"
                  rows="4"
                  placeholder='{"key": "value"}'
                />
              </template>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="ctxDialog = false">Cancel</v-btn>
              <v-btn color="primary" @click="addContext">Add</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>

      <!-- Dependencies Tab -->
      <v-window-item value="dependencies">
        <v-card>
          <v-card-text>
            <div class="d-flex align-center mb-3">
              <h4 class="text-subtitle-1">Rule Dependencies</h4>
              <v-spacer />
              <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="depDialog = true">
                Add Dependency
              </v-btn>
            </div>
            <v-list v-if="rule.dependencies?.length">
              <v-list-item v-for="dep in rule.dependencies" :key="dep.id">
                <v-list-item-title>
                  {{ ruleNameById(dep.parent_rule_id) }} (Rule #{{ dep.parent_rule_id }}) &middot; lookback {{ dep.lookback_minutes }}min
                  <v-chip size="x-small" :color="dep.require_success ? 'success' : 'warning'" class="ml-2">
                    {{ dep.require_success ? "require success" : "require no success" }}
                  </v-chip>
                </v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteDep(dep.id)" />
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-center text-grey py-4">No dependencies</div>
          </v-card-text>
        </v-card>

        <v-dialog v-model="depDialog" max-width="500">
          <v-card>
            <v-card-title>Add Dependency</v-card-title>
            <v-card-text>
              <v-autocomplete
                v-model="depForm.parent_rule_id"
                :items="otherRuleItems"
                item-title="_label"
                item-value="id"
                label="Parent Rule"
                variant="outlined"
                class="mb-3"
              />
              <v-text-field v-model.number="depForm.lookback_minutes" label="Lookback (min)" type="number" variant="outlined" />
              <v-switch v-model="depForm.require_success" label="Require Success" color="primary" />
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="depDialog = false">Cancel</v-btn>
              <v-btn color="primary" @click="addDep">Add</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </v-window-item>

      <!-- Executions Tab -->
      <v-window-item value="executions">
        <v-card>
          <v-data-table
            :headers="execHeaders"
            :items="executions"
            :loading="execLoading"
            item-value="id"
            hover
            @click:row="(_, { item }) => openLiveExecution(item.id)"
          >
            <template #item.status="{ item }">
              <v-chip
                :color="statusColor(item.status)"
                size="small"
              >
                {{ item.status }}
              </v-chip>
            </template>
            <template #item.started_at="{ item }">
              {{ formatDate(item.started_at) }}
            </template>
            <template #item.completed_at="{ item }">
              {{ item.completed_at ? formatDate(item.completed_at) : '-' }}
            </template>
            <template #item._duration="{ item }">
              {{ formatDuration(item.started_at, item.completed_at) }}
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- Live Run Tab -->
      <v-window-item value="liverun">
        <v-row v-if="liveExecution">
          <!-- Live timeline + status -->
          <v-col cols="12" md="6">
            <v-card class="live-card">
              <v-card-text>
                <div class="d-flex align-center mb-4">
                  <v-avatar
                    :color="statusColor(liveExecution.status)"
                    size="44"
                    variant="tonal"
                    class="mr-3"
                  >
                    <v-icon>{{ liveStatusIcon }}</v-icon>
                  </v-avatar>
                  <div class="flex-grow-1">
                    <div class="text-overline text-medium-emphasis">Execution #{{ liveExecution.id }}</div>
                    <div class="text-h6 font-weight-bold">
                      {{ liveExecution.status }}
                      <v-progress-circular
                        v-if="livePolling"
                        indeterminate
                        size="16"
                        width="2"
                        color="info"
                        class="ml-2"
                      />
                    </div>
                    <div class="text-caption text-medium-emphasis">
                      Started {{ formatDate(liveExecution.started_at) }}
                      <span v-if="liveExecution.completed_at">
                        &middot; {{ formatDuration(liveExecution.started_at, liveExecution.completed_at) }}
                      </span>
                    </div>
                  </div>
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    size="small"
                    title="Close live view"
                    @click="closeLiveExecution"
                  />
                </div>

                <v-alert
                  v-if="liveExecution.error"
                  type="error"
                  variant="tonal"
                  class="mb-4"
                  density="compact"
                >
                  {{ liveExecution.error }}
                </v-alert>

                <div class="text-overline text-medium-emphasis mb-2">Steps</div>
                <v-timeline side="end" density="compact" class="live-timeline">
                  <v-timeline-item
                    v-for="step in rule.steps || []"
                    :key="step.id"
                    :icon="liveStepIcon(step)"
                    :dot-color="liveStepColor(step)"
                    size="x-small"
                  >
                    <div class="d-flex align-center">
                      <div class="flex-grow-1">
                        <div
                          class="text-body-2 font-weight-medium"
                          :class="{ 'text-primary': step.id === liveExecution.current_step_id }"
                        >
                          {{ step.name || humanize(step.step_type) }}
                        </div>
                        <div class="text-caption text-medium-emphasis">{{ step.step_type }}</div>
                      </div>
                      <v-chip
                        v-if="step.id === liveExecution.current_step_id && livePolling"
                        size="x-small"
                        color="info"
                        variant="tonal"
                      >
                        running
                      </v-chip>
                    </div>
                  </v-timeline-item>
                </v-timeline>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Pipeline data viewer -->
          <v-col cols="12" md="6">
            <v-card class="live-card">
              <v-card-text>
                <div class="d-flex align-center mb-3">
                  <div>
                    <div class="text-overline text-medium-emphasis">Pipeline Data</div>
                    <div class="text-body-2 text-medium-emphasis">
                      Live view of the data dictionary as steps run.
                    </div>
                  </div>
                  <v-spacer />
                  <v-btn
                    size="small"
                    variant="text"
                    :prepend-icon="livePolling ? 'mdi-pause' : 'mdi-play'"
                    @click="toggleLivePolling"
                  >
                    {{ livePolling ? 'Pause' : 'Resume' }}
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    prepend-icon="mdi-content-copy"
                    @click="copyPipelineData"
                  >
                    Copy
                  </v-btn>
                </div>

                <div v-if="pipelineKeys.length" class="mb-3">
                  <v-chip
                    v-for="k in pipelineKeys"
                    :key="k"
                    size="x-small"
                    variant="tonal"
                    class="mr-1 mb-1 cc-code"
                  >
                    {{ k }}
                  </v-chip>
                </div>

                <pre class="live-json">{{ pipelineDataPretty }}</pre>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
        <v-card v-else>
          <v-card-text class="text-center text-medium-emphasis py-8">
            <v-icon size="48" class="mb-2">mdi-flash-outline</v-icon>
            <div>Run a Test Run to see live pipeline state.</div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
  </div>
  <div v-else class="text-center py-8">
    <v-progress-circular indeterminate />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { formatDateTime, getAppTimezone, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";
import PipelineBuilder from "../../components/pipeline/PipelineBuilder.vue";

const route = useRoute();
const ruleId = computed(() => Number(route.params.id));

const rule = ref(null);
const tab = ref("settings");
const executing = ref(false);
const { snack, snackText, snackColor, notify } = useNotify();

// Reference data from API
const allSensors = ref([]);
const allRooms = ref([]);
const allRules = ref([]);
const allPersons = ref([]);
const telegramDefaultChatIds = ref([]);

const sensorItems = computed(() =>
  allSensors.value.map((s) => ({
    ...s,
    _label: `${s.name || s.id} (${s.sensor_type}${s.room_name ? ', ' + s.room_name : ''})`,
  }))
);

const roomNames = computed(() => allRooms.value.map((r) => r.name));
const personIds = computed(() => allPersons.value.map((p) => p.id));

const otherRuleItems = computed(() =>
  allRules.value
    .filter((r) => r.id !== ruleId.value)
    .map((r) => ({ ...r, _label: `${r.name} (#${r.id})` }))
);

const triggerTypes = [
  { title: "Sensor Event", value: "sensor_event" },
  { title: "Cron Schedule", value: "cron" },
  { title: "Manual", value: "manual" },
  { title: "Webhook", value: "webhook" },
  { title: "Occupancy Duration", value: "occupancy_duration" },
  { title: "Telegram Command", value: "telegram" },
];

const contextTypeItems = [
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
];

const dayItems = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const activityTypeItems = [
  "eating", "sleeping", "medication", "bathing", "walking",
  "watching_tv", "reading", "exercising", "cooking", "socializing",
];

// Settings form
const form = ref({});

// Contexts
const ctxDialog = ref(false);
const ctxForm = ref({ context_type: "room", config: {}, negate: false });
const ctxConfigStr = ref("{}");

// Dependencies
const depDialog = ref(false);
const depForm = ref({ parent_rule_id: 0, lookback_minutes: 30, require_success: true });

// Executions
const executions = ref([]);
const execLoading = ref(false);
const execHeaders = [
  { title: "ID", key: "id" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Completed", key: "completed_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Duration", key: "_duration" },
];

// Live execution view (polled while running)
const liveExecutionId = ref(null);
const liveExecution = ref(null);
const livePolling = ref(false);
let livePollTimer = null;

const pipelineDataPretty = computed(() => {
  const data = liveExecution.value?.pipeline_data_json || {};
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
});

const pipelineKeys = computed(() => Object.keys(liveExecution.value?.pipeline_data_json || {}));

const liveStatusIcon = computed(() => {
  const map = {
    completed: "mdi-check-circle",
    failed: "mdi-alert-circle",
    running: "mdi-flash",
    waiting: "mdi-clock-outline",
    cancelled: "mdi-cancel",
  };
  return map[liveExecution.value?.status] || "mdi-flash-outline";
});

function humanize(s) {
  if (!s) return "";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function liveStepIcon(step) {
  const map = {
    llm_call: "mdi-brain",
    logic_reasoning: "mdi-sitemap-outline",
    notification: "mdi-bell-outline",
    verification: "mdi-check-decagram-outline",
    web_search: "mdi-magnify",
    image_generation: "mdi-image-outline",
    eink_render: "mdi-image-edit-outline",
  };
  return map[step.step_type] || "mdi-cog-outline";
}

function liveStepColor(step) {
  if (!liveExecution.value) return "grey";
  const status = liveExecution.value.status;
  const currentId = liveExecution.value.current_step_id;
  const steps = (rule.value?.steps || []).slice().sort((a, b) => a.order - b.order);
  const currentStep = steps.find((s) => s.id === currentId);
  const currentOrder = currentStep ? currentStep.order : null;

  if (status === "completed") return "success";
  if (status === "failed" && step.id === currentId) return "error";

  if (currentOrder !== null) {
    if (step.order < currentOrder) return "success";
    if (step.id === currentId) return status === "failed" ? "error" : "info";
  }
  return "grey";
}

function openLiveExecution(id) {
  liveExecutionId.value = id;
  tab.value = "liverun";
  fetchLiveExecution();
  startLivePolling();
}

function closeLiveExecution() {
  stopLivePolling();
  liveExecutionId.value = null;
  liveExecution.value = null;
  if (tab.value === "liverun") tab.value = "executions";
}

async function fetchLiveExecution() {
  if (!liveExecutionId.value) return;
  try {
    const exec = await api.getWorkflow(liveExecutionId.value);
    liveExecution.value = exec;
    if (!["running", "waiting"].includes(exec.status)) {
      stopLivePolling();
      // Refresh executions list to show the final status
      loadExecutions();
    }
  } catch (e) {
    console.error("Failed to fetch live execution:", e);
    stopLivePolling();
  }
}

function startLivePolling() {
  stopLivePolling();
  livePolling.value = true;
  livePollTimer = setInterval(fetchLiveExecution, 750);
}

function stopLivePolling() {
  livePolling.value = false;
  if (livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
}

function toggleLivePolling() {
  if (livePolling.value) {
    stopLivePolling();
  } else {
    startLivePolling();
    fetchLiveExecution();
  }
}

async function copyPipelineData() {
  try {
    await navigator.clipboard.writeText(pipelineDataPretty.value);
    notify("Pipeline data copied");
  } catch {
    notify("Copy failed", "error");
  }
}

function sensorIcon(type) {
  const map = {
    camera: "mdi-cctv",
    presence: "mdi-motion-sensor",
    button: "mdi-gesture-tap-button",
    light: "mdi-lightbulb",
    eink: "mdi-image-edit",
  };
  return map[type] || "mdi-access-point";
}

function ctxIcon(type) {
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

function ctxSummary(ctx) {
  const c = ctx.config_json || {};
  switch (ctx.context_type) {
    case "room": return c.room_name || "Any room";
    case "time_range": return `${c.start_time || '?'} - ${c.end_time || '?'}`;
    case "day_of_week": return Array.isArray(c.days) ? c.days.join(", ") : JSON.stringify(c);
    case "person_presence":
      return `${c.person_id || 'any person'} is ${c.status || '?'}${c.room_name ? ' in ' + c.room_name : ''}${c.use_semantic_memory ? ' (semantic)' : ''}`;
    case "person_activity": return `${c.person_id || 'any person'}: ${c.activity_type || '?'}`;
    case "home_state": return `${c.person_id || 'any person'} state = ${c.state || '?'}`;
    case "presence_status": return `${c.person_id || 'any person'}: ${c.status || '?'}` + (c.room_name ? ` in ${c.room_name}` : "");
    case "presence_dwell": return `${c.person_id || 'any person'}: ${c.status || 'any status'} ≥ ${c.min_minutes || '?'} min`;
    case "scene_contains": {
      const parts = [];
      if (c.objects_any?.length) parts.push(`objects: ${c.objects_any.join(", ")}`);
      if (c.hazard_flags_any?.length) parts.push(`hazards: ${c.hazard_flags_any.join(", ")}`);
      return parts.length ? parts.join(" + ") : "Any scene";
    }
    case "person_movement_memory":
      return `${c.person_id || 'any person'}: ${c.semantic || 'any'}${c.to_room_id ? ' → ' + c.to_room_id : ''}`;
    default: return JSON.stringify(c);
  }
}

function ruleNameById(id) {
  const r = allRules.value.find((r) => r.id === id);
  return r ? r.name : "";
}

function openCtxDialog() {
  ctxForm.value = { context_type: "room", config: {}, negate: false };
  ctxConfigStr.value = "{}";
  ctxDialog.value = true;
}

function seedCtxConfig(type) {
  switch (type) {
    case "home_state":      return { state: "at_home" };
    case "presence_status": return { status: "present_room" };
    case "presence_dwell":  return { status: "", min_minutes: 5 };
    default: return {};
  }
}

async function loadRule() {
  try {
    rule.value = await api.getRule(ruleId.value);
    form.value = {
      name: rule.value.name,
      description: rule.value.description || "",
      enabled: rule.value.enabled,
      trigger_type: rule.value.trigger_type,
      schedule_cron: rule.value.schedule_cron || "",
      primary_sensor_id: rule.value.primary_sensor_id || "",
      cool_off_minutes: rule.value.cool_off_minutes,
      max_daily_triggers: rule.value.max_daily_triggers,
      max_concurrent_executions: rule.value.max_concurrent_executions ?? 1,
      execution_timeout_minutes: rule.value.execution_timeout_minutes ?? 5,
      occupancy_config: rule.value.occupancy_config || { min_minutes: 40 },
      telegram_trigger_config: (() => {
        const cfg = rule.value.telegram_trigger_config || {};
        const ids = cfg.allowed_chat_ids?.length
          ? cfg.allowed_chat_ids
          : telegramDefaultChatIds.value;
        return {
          command: cfg.command ?? "",
          allowed_chat_ids: [...ids],
          respond_with_ack: cfg.respond_with_ack ?? true,
        };
      })(),
    };
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadTelegramDefaults() {
  try {
    const data = await api.getTelegramTriggerDefaults();
    telegramDefaultChatIds.value = data?.allowed_chat_ids ?? [];
  } catch {
    telegramDefaultChatIds.value = [];
  }
}

async function loadReferenceData() {
  const [sensors, rooms, rules, persons] = await Promise.all([
    api.getSensors().catch(() => []),
    api.getRooms().catch(() => []),
    api.getRules().catch(() => []),
    api.getPersons().catch(() => []),
  ]);
  allSensors.value = Array.isArray(sensors) ? sensors : [];
  allRooms.value = Array.isArray(rooms) ? rooms : [];
  allRules.value = Array.isArray(rules) ? rules : [];
  allPersons.value = Array.isArray(persons) ? persons : [];
}

async function saveSettings() {
  if (form.value.trigger_type === "telegram") {
    const ids = form.value.telegram_trigger_config?.allowed_chat_ids ?? [];
    if (!ids.length) {
      notify("Allowed Chat IDs are required for Telegram trigger rules.", "error");
      return;
    }
  }
  try {
    await api.updateRule(ruleId.value, form.value);
    await loadRule();
    notify("Settings saved");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function executeRule() {
  executing.value = true;
  try {
    const result = await api.executeRule(ruleId.value);
    notify(`Execution started (#${result.execution_id})`);
    if (result.execution_id) {
      openLiveExecution(result.execution_id);
    }
    await loadExecutions();
  } catch (e) {
    notify(e.message, "error");
  }
  executing.value = false;
}

async function addContext() {
  try {
    let config;
    const t = ctxForm.value.context_type;
    if (["room", "time_range", "day_of_week", "person_presence", "person_activity", "scene_contains", "person_movement_memory"].includes(t)) {
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
    await loadRule();
    notify("Context added");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteContext(ctxId) {
  try {
    await api.deleteRuleContext(ruleId.value, ctxId);
    await loadRule();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function addDep() {
  try {
    await api.addRuleDep(ruleId.value, depForm.value);
    depDialog.value = false;
    await loadRule();
    notify("Dependency added");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteDep(depId) {
  try {
    await api.deleteRuleDep(ruleId.value, depId);
    await loadRule();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadExecutions() {
  execLoading.value = true;
  try {
    executions.value = await api.getWorkflows({ rule_id: ruleId.value, limit: 50 });
  } catch (e) {
    console.error("Failed to load executions:", e);
    executions.value = [];
  }
  execLoading.value = false;
}

function statusColor(status) {
  const map = { completed: "success", failed: "error", running: "info", waiting: "warning", cancelled: "grey" };
  return map[status] || "grey";
}

const formatDate = formatDateTime;

function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return "-";
  const ms = new Date(endIso) - new Date(startIso);
  if (ms < 0) return "-";
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`;
}

watch(tab, (val) => {
  if (val === "executions") loadExecutions();
});

// Back-fill system defaults into the form as soon as they arrive from the API.
// Runs whether the defaults load before or after the rule data.
watch(telegramDefaultChatIds, (defaults) => {
  if (
    form.value.trigger_type === "telegram" &&
    !form.value.telegram_trigger_config?.allowed_chat_ids?.length &&
    defaults.length
  ) {
    form.value.telegram_trigger_config = {
      ...form.value.telegram_trigger_config,
      allowed_chat_ids: [...defaults],
    };
  }
});

// Seed default config when context_type changes in the filter dialog.
watch(() => ctxForm.value.context_type, (type) => {
  const defaults = seedCtxConfig(type);
  if (Object.keys(defaults).length > 0) {
    for (const [key, value] of Object.entries(defaults)) {
      if (ctxForm.value.config[key] === undefined || ctxForm.value.config[key] === null) {
        ctxForm.value.config[key] = value;
      }
    }
  }
});

onMounted(async () => {
  await loadTelegramDefaults();   // must resolve before loadRule so the IIFE sees the defaults
  loadRule();
  loadReferenceData();
});

onBeforeUnmount(() => {
  stopLivePolling();
});
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}

.live-card {
  min-height: 480px;
}

.live-timeline {
  max-height: 420px;
  overflow-y: auto;
  padding-right: 8px;
}

.live-json {
  background: var(--cc-surface-3);
  border: 1px solid var(--cc-divider);
  border-radius: 12px;
  padding: 14px 16px;
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 520px;
  overflow: auto;
  white-space: pre;
  color: var(--cc-text-1);
}

.cc-code {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
</style>
