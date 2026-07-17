<template>
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
                  {{ item.raw.sensor_type }} · {{ item.raw.room_name || "No room" }}
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-col>
        <v-col v-if="form.trigger_type === 'cron'" cols="12">
          <CronBuilder v-model="form.schedule_cron" :timezone="getAppTimezone()" />
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
              :rules="[
                (v) => (Array.isArray(v) && v.length > 0) || 'At least one chat ID is required',
              ]"
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
          <v-text-field
            v-model.number="form.cool_off_minutes"
            label="Cool-off (min)"
            type="number"
            variant="outlined"
            hint="Minimum minutes between executions (0 = no limit)"
            persistent-hint
          />
        </v-col>
        <v-col cols="6" md="3">
          <v-text-field
            v-model.number="form.max_daily_triggers"
            label="Max Daily"
            type="number"
            variant="outlined"
            hint="Maximum executions per day (0 = no limit)"
            persistent-hint
          />
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
      <v-btn color="primary" @click="$emit('save')">Save Settings</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import CronBuilder from "../pipeline/CronBuilder.vue";
import { sensorIcon } from "@/composables/useRuleDetail.js";
import { getAppTimezone } from "@/services/timezone.js";

defineProps({
  triggerTypes: { type: Array, required: true },
  sensorItems: { type: Array, required: true },
});
defineEmits(["save"]);

const form = defineModel("form", { type: Object, required: true });
</script>
