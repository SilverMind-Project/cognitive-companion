<!-- Backend: backend/steps/builtin/notification.py -->
<template>
  <!-- General tab -->
  <div v-if="tab === 'general'">
    <v-select
      :model-value="modelValue.alert_level"
      :items="['emergency', 'warning', 'info', 'reminder']"
      label="Alert Level"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, alert_level: $event })"
    />
    <v-combobox
      :model-value="modelValue.channels"
      :items="availableChannels"
      label="Notification Channels"
      multiple
      chips
      closable-chips
      hint="Select channels or type custom channel names. Leave empty to use defaults from notifications.yaml."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, channels: $event })"
    />
    <v-checkbox
      :model-value="modelValue.trigger_cooloff"
      label="Trigger cool-off upon execution"
      hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
    />
  </div>

  <!-- Templates tab -->
  <div v-else-if="tab === 'templates'">
    <v-textarea
      :model-value="modelValue.message_template"
      label="Default Message Template"
      rows="3"
      hint="Default for all channels. Use {{message}}, {{room_name}}, {{vision_response}}, {{logic_response.user_notification}}, etc."
      persistent-hint
      class="mb-5"
      @update:model-value="emit('update:modelValue', { ...modelValue, message_template: $event })"
    />
    <div class="text-overline text-medium-emphasis mb-2">Per-Channel Overrides</div>
    <v-textarea
      :model-value="modelValue.telegram_template"
      label="Telegram Template"
      rows="3"
      hint="HTML supported. Use {{message}}, {{room_name}}, etc. Falls back to the default template."
      persistent-hint
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, telegram_template: $event })"
    />
    <v-textarea
      :model-value="modelValue.eink_template"
      label="E-Ink Template"
      rows="2"
      hint="Short plain-text for e-ink displays. Use {{message}}, {{room_name}}, etc."
      persistent-hint
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, eink_template: $event })"
    />
    <v-textarea
      :model-value="modelValue.ha_speaker_tts_template"
      label="HA Speaker TTS / PWA Announcement Template"
      rows="2"
      hint="Natural language for spoken announcements. Use {{message}}, {{room_name}}, etc."
      persistent-hint
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, ha_speaker_tts_template: $event })"
    />
    <v-textarea
      :model-value="modelValue.pwa_popup_text_template"
      label="PWA Popup Text Template"
      rows="2"
      hint="Notification text shown in the companion UI overlay. Use {{message}}, {{room_name}}, etc."
      persistent-hint
      class="mb-3"
      @update:model-value="emit('update:modelValue', { ...modelValue, pwa_popup_text_template: $event })"
    />
    <v-textarea
      :model-value="modelValue.pwa_realtime_ai_template"
      label="PWA Realtime AI Template"
      rows="2"
      hint="Conversational voice prompt for Gemini Live delivery. Use {{message}}, {{room_name}}, etc."
      persistent-hint
      @update:model-value="emit('update:modelValue', { ...modelValue, pwa_realtime_ai_template: $event })"
    />
  </div>

  <!-- Channel Options tab -->
  <div v-else-if="tab === 'channels'">
    <!-- Telegram -->
    <div v-if="modelValue.channels && modelValue.channels.includes('telegram')">
      <div class="text-overline text-medium-emphasis mb-2">Telegram</div>
      <v-select
        :model-value="modelValue.telegram_image_source"
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
        @update:model-value="emit('update:modelValue', { ...modelValue, telegram_image_source: $event })"
      />
      <template v-if="modelValue.telegram_image_source === 'additional' || modelValue.telegram_image_source === 'both'">
        <v-combobox
          :model-value="modelValue.telegram_additional_sensor_ids"
          :items="cameraSensorItems"
          label="Camera Sensors (in order)"
          multiple chips closable-chips
          hint="Pull images from these camera sensors."
          persistent-hint
          class="mb-4"
          @update:model-value="emit('update:modelValue', { ...modelValue, telegram_additional_sensor_ids: $event })"
        />
        <v-combobox
          :model-value="modelValue.telegram_additional_room_names"
          :items="availableRooms"
          label="Additional Rooms"
          multiple chips closable-chips
          hint="Pull images from all cameras in these rooms."
          persistent-hint
          class="mb-4"
          @update:model-value="emit('update:modelValue', { ...modelValue, telegram_additional_room_names: $event })"
        />
        <v-card variant="tonal" class="mb-4 pa-4">
          <v-checkbox
            :model-value="modelValue.telegram_sort_by_sensor_then_time"
            label="Group by sensor, then chronological within each sensor"
            hide-details
            @update:model-value="emit('update:modelValue', { ...modelValue, telegram_sort_by_sensor_then_time: $event })"
          />
          <div class="text-caption text-medium-emphasis ml-8 mt-2">
            Enables inter-frame temporal analysis per camera.
          </div>
          <v-text-field
            v-if="modelValue.telegram_sort_by_sensor_then_time"
            :model-value="modelValue.telegram_images_per_sensor"
            label="Images per sensor"
            density="compact"
            type="number"
            :min="1"
            class="mt-3"
            @update:model-value="emit('update:modelValue', { ...modelValue, telegram_images_per_sensor: Number($event) || 1 })"
          />
        </v-card>
        <TimeFilterCard
          :model-value="modelValue.telegram_image_time_filter || {}"
          @update:model-value="emit('update:modelValue', { ...modelValue, telegram_image_time_filter: $event })"
        />
      </template>
      <v-divider class="mb-4" />
    </div>

    <!-- E-Ink -->
    <div v-if="modelValue.channels && modelValue.channels.includes('eink')">
      <div class="text-overline text-medium-emphasis mb-2">E-Ink Display</div>
      <v-combobox
        :model-value="modelValue.eink_targets"
        :items="einkSensorItems"
        label="E-Ink Target Devices"
        multiple chips closable-chips
        hint="Select e-ink displays. Leave empty to dispatch to all e-ink devices."
        persistent-hint
        class="mb-4"
        @update:model-value="emit('update:modelValue', { ...modelValue, eink_targets: $event })"
      />
      <v-select
        :model-value="modelValue.eink_template_id"
        :items="imageTemplateItems"
        :item-title="(item) => item.name || `Template #${item.id}`"
        :item-value="(item) => item.id"
        label="Image Template"
        clearable
        hint="Select an image template for the notification. Leave empty to use the default alert template."
        persistent-hint
        class="mb-4"
        @update:model-value="emit('update:modelValue', { ...modelValue, eink_template_id: $event })"
      />
      <v-text-field
        :model-value="modelValue.eink_expiry_minutes"
        label="Expiry Duration (minutes)"
        type="number"
        :min="1"
        hint="Number of minutes before the display reverts to the default template. Default: 30."
        persistent-hint
        class="mb-5"
        @update:model-value="emit('update:modelValue', { ...modelValue, eink_expiry_minutes: Number($event) || 30 })"
      />
    </div>

    <!-- HA Speaker TTS -->
    <div v-if="modelValue.channels && modelValue.channels.includes('ha_speaker_tts')">
      <div class="text-overline text-medium-emphasis mb-2">HA Speaker TTS</div>
      <v-autocomplete
        :model-value="modelValue.ha_media_player"
        :items="haMediaPlayerItems"
        :item-title="(item) => item.name || item.entity_id || item"
        :item-value="(item) => item.entity_id || item"
        label="TTS Media Player"
        clearable
        hint="Home Assistant media_player entity for TTS audio playback"
        persistent-hint
        class="mb-3"
        @update:model-value="emit('update:modelValue', { ...modelValue, ha_media_player: $event })"
      />
      <v-text-field
        :model-value="modelValue.tts_language"
        label="TTS Language"
        clearable
        placeholder="e.g. ta, en"
        hint="Language code for TTS synthesis. Leave blank to use the server default."
        persistent-hint
        class="mb-3"
        @update:model-value="emit('update:modelValue', { ...modelValue, tts_language: $event })"
      />
      <v-select
        :model-value="modelValue.tts_style"
        :items="['', 'neutral', 'clear', 'formal', 'chat', 'happy', 'surprise', 'sad', 'fear', 'anger', 'disgust', 'narrative', 'enthusiastic', 'laugh', 'yawn', 'angry']"
        label="TTS Style"
        clearable
        hint="Svara speaking style. Leave blank to use the server default."
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, tts_style: $event })"
      />
    </div>

    <!-- Webhook -->
    <div v-if="modelValue.channels && modelValue.channels.includes('webhook')" class="mt-5">
      <div class="text-overline text-medium-emphasis mb-2">Webhook</div>
      <v-text-field
        :model-value="modelValue.webhook_url"
        label="Webhook URL (optional)"
        clearable
        hint="Override global webhook endpoint (from settings/env)"
        persistent-hint
        class="mb-3"
        @update:model-value="emit('update:modelValue', { ...modelValue, webhook_url: $event })"
      />
      <v-textarea
        :model-value="modelValue.webhook_template"
        label="Webhook JSON Template (optional)"
        rows="5"
        hint="JSON payload template. Use {{message}}, {{room_name}}, etc. Falls back to a basic JSON envelope."
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, webhook_template: $event })"
      />
    </div>

    <v-alert
      v-if="(!modelValue.channels || (!modelValue.channels.includes('telegram') && !modelValue.channels.includes('ha_speaker_tts') && !modelValue.channels.includes('webhook') && !modelValue.channels.includes('eink')))"
      type="info" variant="tonal" density="compact" class="mt-3"
    >
      Add <code>telegram</code>, <code>ha_speaker_tts</code>, <code>eink</code>, or <code>webhook</code> on the General tab to configure their per-channel options here.
    </v-alert>
  </div>
</template>

<script>
import TimeFilterCard from "./_shared/TimeFilterCard.vue";

export const stepDefaults = {
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
};
export const stepTabs = [
  { key: "templates", label: "Templates", icon: "mdi-message-text-outline" },
  { key: "channels", label: "Channel Options", icon: "mdi-tune" },
];

export function beforeSave(cfg) {
  return cfg;
}

export function onStepLoaded(cfg) {
  // Time filter normalization handled by TimeFilterCard internally
}
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "general" },
  cameraSensorItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
  availableChannels: { type: Array, default: () => [] },
  einkSensorItems: { type: Array, default: () => [] },
  haMediaPlayerItems: { type: Array, default: () => [] },
  imageTemplateItems: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>
