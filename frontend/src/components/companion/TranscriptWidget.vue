<template>
  <div class="transcript-card">
    <!-- Header -->
    <div class="transcript-header">
      <v-icon size="18" color="rgba(255,255,255,0.5)" class="mr-2">mdi-message-text</v-icon>
      <span class="header-title">Conversation</span>
      <v-spacer />
      <button
        v-if="transcript.length"
        class="clear-btn"
        title="Clear conversation"
        @click="$emit('clear')"
      >
        <v-icon size="16">mdi-delete-sweep</v-icon>
      </button>
    </div>

    <!-- Messages -->
    <div class="messages-scroll" ref="scrollRef">
      <!-- Empty state -->
      <div v-if="transcript.length === 0" class="empty-state">
        <v-icon size="52" color="rgba(255,255,255,0.12)" class="mb-4">mdi-chat-sleep-outline</v-icon>
        <p class="empty-title">No conversation yet</p>
        <p class="empty-hint">Tap the microphone to start talking with Nanai</p>
      </div>

      <!-- Messages -->
      <template v-else>
        <div
          v-for="(msg, i) in transcript"
          :key="i"
          class="message-row"
          :class="msg.source === 'user' ? 'message-row--right' : 'message-row--left'"
        >
          <!-- Avatar -->
          <div v-if="msg.source !== 'user'" class="avatar avatar--ai">
            <v-icon size="16" color="rgba(196,181,253,0.9)">mdi-robot-happy-outline</v-icon>
          </div>

          <!-- Bubble -->
          <div class="bubble" :class="msg.source === 'user' ? 'bubble--user' : 'bubble--ai'">
            <p class="bubble-text">{{ msg.text }}</p>
            <span class="bubble-time">
              {{ msg.source === "user" ? "You" : "Nanai" }}
              <span v-if="msg.timestamp" class="ml-1 opacity-60">&middot; {{ formatTime(msg.timestamp) }}</span>
            </span>
          </div>

          <div v-if="msg.source === 'user'" class="avatar avatar--user">
            <v-icon size="16" color="rgba(167,139,250,0.9)">mdi-account</v-icon>
          </div>
        </div>
      </template>

      <!-- Spacer so last message isn't flush against bottom -->
      <div class="scroll-spacer" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from "vue";

const props = defineProps({
  transcript: { type: Array, default: () => [] },
});

defineEmits(["clear"]);

const scrollRef = ref(null);

watch(
  () => props.transcript.length,
  () => {
    nextTick(() => {
      if (scrollRef.value) {
        scrollRef.value.scrollTop = scrollRef.value.scrollHeight;
      }
    });
  },
);

function formatTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

<style scoped>
/* ── Card ───────────────────────────────────────────────────────────────── */
.transcript-card {
  background: rgba(22, 20, 38, 0.72);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 24px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 340px;
  overflow: hidden;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.transcript-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.header-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.75);
  letter-spacing: 0.02em;
}

.clear-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.30);
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: color 0.2s;
}

.clear-btn:hover {
  color: rgba(255, 255, 255, 0.65);
}

/* ── Scroll area ────────────────────────────────────────────────────────── */
.messages-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 0;
  scroll-behavior: smooth;
}

.messages-scroll::-webkit-scrollbar {
  width: 4px;
}

.messages-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.messages-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 4px;
}

.scroll-spacer { height: 16px; }

/* ── Empty state ────────────────────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-title {
  font-size: 1rem;
  color: rgba(255, 255, 255, 0.35);
  margin: 0 0 6px;
}

.empty-hint {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.22);
  margin: 0;
  max-width: 240px;
}

/* ── Message row ────────────────────────────────────────────────────────── */
.message-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin-bottom: 14px;
}

.message-row--right {
  flex-direction: row-reverse;
}

/* ── Avatars ────────────────────────────────────────────────────────────── */
.avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 2px;
}

.avatar--ai   { background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.25); }
.avatar--user { background: rgba(99,  102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.25); }

/* ── Bubbles ────────────────────────────────────────────────────────────── */
.bubble {
  max-width: 76%;
  padding: 10px 14px 8px;
  border-radius: 16px;
}

.bubble--user {
  background: rgba(99, 102, 241, 0.22);
  border: 1px solid rgba(99, 102, 241, 0.28);
  border-bottom-right-radius: 4px;
}

.bubble--ai {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-bottom-left-radius: 4px;
}

.bubble-text {
  font-size: 0.92rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.88);
  margin: 0 0 4px;
  word-break: break-word;
}

.bubble-time {
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.35);
}
</style>
