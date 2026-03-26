<template>
  <v-card class="glass-card fill-height d-flex flex-column" rounded="xl">
    <v-card-title class="d-flex align-center">
      <v-icon class="mr-2">mdi-message-text</v-icon>
      Conversation
      <v-spacer />
      <v-btn
        v-if="transcript.length"
        icon="mdi-delete-sweep"
        size="x-small"
        variant="text"
        title="Clear transcript"
        @click="$emit('clear')"
      />
    </v-card-title>

    <v-card-text class="flex-grow-1 overflow-y-auto pa-3" ref="transcriptPanel">
      <div v-for="(msg, i) in transcript" :key="i" class="mb-3 d-flex" :class="msg.source === 'user' ? 'justify-end' : 'justify-start'">
        <div :class="['chat-bubble', msg.source === 'user' ? 'bubble-user' : 'bubble-assistant']">
          <div class="bubble-content text-body-2">{{ msg.text }}</div>
          <div class="bubble-meta text-caption">
            {{ msg.source === 'user' ? 'You' : 'Assistant' }}
            <span v-if="msg.timestamp" class="ml-1">&middot; {{ formatTime(msg.timestamp) }}</span>
          </div>
        </div>
      </div>

      <div v-if="transcript.length === 0" class="text-center text-medium-emphasis py-8">
        <v-icon size="64" color="grey-darken-1" class="mb-4">mdi-microphone-off</v-icon>
        <div class="text-body-1">Tap the microphone to start talking</div>
        <div class="text-body-2 mt-1">Your conversation will appear here</div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, watch, nextTick } from "vue";

defineProps({
  transcript: { type: Array, default: () => [] },
});

defineEmits(["clear"]);

const transcriptPanel = ref(null);

watch(
  () => arguments?.[0]?.transcript?.length,
  () => {
    nextTick(() => {
      const el = transcriptPanel.value?.$el;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
);

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
</script>

<style scoped>
.chat-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 16px;
  position: relative;
}

.bubble-user {
  background: rgba(99, 102, 241, 0.25);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-bottom-right-radius: 4px;
}

.bubble-assistant {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-bottom-left-radius: 4px;
}

.bubble-meta {
  opacity: 0.6;
  margin-top: 4px;
}
</style>
