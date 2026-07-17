<template>
  <v-dialog v-model="open" max-width="500">
    <v-card>
      <v-card-title>Add Context Filter</v-card-title>
      <v-card-text>
        <v-select
          v-model="ctxForm.context_type"
          :items="CONTEXT_TYPE_ITEMS"
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
            :items="DAY_ITEMS"
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
            :items="ACTIVITY_TYPE_ITEMS"
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
            :rules="[(v) => !!v || 'Choose a state.']"
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
            :rules="[(v) => !!v || 'Choose a status.']"
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
            :rules="[
              (v) => (Number.isInteger(Number(v)) && v >= 1 && v <= 1440) || 'Must be 1..1440.',
            ]"
            variant="outlined"
            density="compact"
            hide-details="auto"
            rounded="lg"
            hint="Filter triggers only when the person has held the matching status this long."
            persistent-hint
          />
          <v-alert
            v-if="ctxForm.config.min_minutes >= 30"
            type="info"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
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
            :items="[
              'entering',
              'exiting',
              'approaching_exit',
              'entering_depth',
              'stationary',
              'any',
            ]"
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

        <!-- Dementia Signal filter -->
        <template v-else-if="ctxForm.context_type === 'dementia_signal'">
          <v-select
            v-model="ctxForm.config.kinds"
            :items="DEMENTIA_SIGNAL_KINDS"
            label="Signal Kinds (empty = any)"
            multiple
            chips
            closable-chips
            variant="outlined"
            hint="Signal types to match. Leave empty to match all kinds."
            persistent-hint
            class="mb-3"
          />
          <v-autocomplete
            v-model="ctxForm.config.person_ids"
            :items="personIds"
            label="Persons (empty = any)"
            multiple
            chips
            closable-chips
            variant="outlined"
            hint="Person IDs to match. Leave empty to match any person."
            persistent-hint
            class="mb-3"
          />
          <v-select
            v-model="ctxForm.config.min_severity"
            :items="[
              { title: 'Info (any)', value: 0.0 },
              { title: 'Warning', value: 0.66 },
              { title: 'Emergency', value: 1.0 },
            ]"
            label="Minimum Severity"
            variant="outlined"
            class="mb-3"
          />
          <v-text-field
            v-model.number="ctxForm.config.cooldown_minutes"
            label="Cooldown (minutes)"
            variant="outlined"
            type="number"
            :min="0"
            hint="Suppress repeated matches within N minutes per person+kind. 0 = no cooldown."
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
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" @click="$emit('add')">Add</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { getAppTimezone } from "@/services/timezone.js";
import {
  CONTEXT_TYPE_ITEMS,
  DAY_ITEMS,
  ACTIVITY_TYPE_ITEMS,
  DEMENTIA_SIGNAL_KINDS,
} from "@/composables/useRuleContexts.js";

defineProps({
  roomNames: { type: Array, required: true },
  personIds: { type: Array, required: true },
});
defineEmits(["add"]);

const open = defineModel({ type: Boolean, required: true });
const ctxForm = defineModel("ctxForm", { type: Object, required: true });
const ctxConfigStr = defineModel("ctxConfigStr", { type: String, required: true });
</script>
