<template>
  <div
    class="transcript-card"
    :class="expanded ? 'transcript-card--open' : 'transcript-card--closed'"
  >
    <!-- Header (always visible) -->
    <div
      class="transcript-header"
      role="button"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <v-icon size="18" color="var(--cc-text-3)" class="mr-2">mdi-message-text</v-icon>
      <span class="header-title">Conversation</span>
      <span v-if="transcript.length && !expanded" class="message-count">{{
        transcript.length
      }}</span>
      <v-spacer />
      <button
        v-if="transcript.length && expanded"
        class="clear-btn"
        title="Clear conversation"
        @click.stop="$emit('clear')"
      >
        <v-icon size="16">mdi-delete-sweep</v-icon>
      </button>
      <v-icon size="18" class="toggle-chevron" :class="expanded ? 'chevron--up' : ''">
        mdi-chevron-down
      </v-icon>
    </div>

    <!-- Messages (only when expanded) -->
    <div v-if="expanded" ref="scrollRef" class="messages-scroll">
      <!-- Empty state -->
      <div v-if="transcript.length === 0" class="empty-state">
        <v-icon size="52" color="var(--cc-divider-strong)" class="mb-4"
          >mdi-chat-sleep-outline</v-icon
        >
        <p class="empty-title">No conversation yet</p>
        <p class="empty-hint">Tap the microphone to start talking with your companion</p>
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
            <v-icon size="16" color="var(--cc-brand)">mdi-robot-happy-outline</v-icon>
          </div>

          <!-- Bubble -->
          <div class="bubble" :class="msg.source === 'user' ? 'bubble--user' : 'bubble--ai'">
            <p class="bubble-text">{{ msg.text }}</p>
            <span class="bubble-time">
              {{ msg.source === "user" ? "You" : "System" }}
              <span v-if="msg.timestamp" class="ml-1 opacity-60"
                >&middot; {{ formatTime(msg.timestamp) }}</span
              >
            </span>
          </div>

          <div v-if="msg.source === 'user'" class="avatar avatar--user">
            <v-icon size="16" color="var(--sage-600)">mdi-account</v-icon>
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
import { formatTimeOnly } from "../../services/timezone.js";

const props = defineProps({
  transcript: { type: Array, default: () => [] },
});

const expanded = ref(false);

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

const formatTime = formatTimeOnly;
</script>

<style scoped>
/* ── Card — warm DS paper ───────────────────────────────────────────────── */
.transcript-card {
  background: var(--cc-surface);
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-xl);
  box-shadow: var(--cc-shadow-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: border-color var(--cc-dur-base) var(--cc-ease-standard);
}

.transcript-card--open {
  height: 100%;
  min-height: 340px;
}

.transcript-card--closed {
  height: auto;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.transcript-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  flex-shrink: 0;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.3s ease;
}

.transcript-card--open .transcript-header {
  border-bottom-color: var(--cc-divider);
}

.transcript-header:hover .header-title {
  color: var(--cc-text-1);
}

.message-count {
  font-size: 0.72rem;
  font-weight: 700;
  background: var(--sage-50);
  border: 1px solid var(--sage-200);
  color: var(--sage-600);
  border-radius: var(--cc-radius-pill);
  padding: 1px 8px;
  margin-left: 8px;
}

.toggle-chevron {
  color: var(--cc-text-3);
  transition: transform var(--cc-dur-base) var(--cc-ease-standard);
}

.chevron--up {
  transform: rotate(180deg);
}

.header-title {
  font-family: var(--cc-font-display);
  font-size: 1.25rem;
  font-weight: 500;
  color: var(--cc-text-1);
  letter-spacing: -0.01em;
}

.clear-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--cc-text-3);
  padding: 4px;
  border-radius: var(--cc-radius-xs);
  display: flex;
  align-items: center;
  transition: color var(--cc-dur-fast) var(--cc-ease-standard);
}

.clear-btn:hover {
  color: var(--cc-text-1);
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
  background: var(--cc-divider-strong);
  border-radius: 4px;
}

.scroll-spacer {
  height: 16px;
}

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
  font-size: 1.25rem;
  color: var(--cc-text-2);
  margin: 0 0 6px;
}

.empty-hint {
  font-size: 1rem;
  color: var(--cc-text-3);
  margin: 0;
  max-width: 260px;
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

.avatar--ai {
  background: var(--sage-50);
  border: 1px solid var(--sage-200);
}
.avatar--user {
  background: var(--sage-50);
  border: 1px solid var(--line-brand);
}

/* ── Bubbles (DS TranscriptBubble) ──────────────────────────────────────── */
.bubble {
  max-width: 85%;
  padding: 14px 20px;
  border-radius: var(--cc-radius-lg);
}

/* Senior's own words: large serif italic on a soft sage card */
.bubble--user {
  background: var(--sage-50);
  border: 1px solid var(--line-brand);
  border-bottom-right-radius: var(--cc-radius-xs);
}

/* Companion answer: warm paper card */
.bubble--ai {
  background: var(--cc-surface);
  border: 1px solid var(--cc-divider);
  box-shadow: var(--cc-shadow-xs);
  border-bottom-left-radius: var(--cc-radius-xs);
}

.bubble-text {
  font-size: 20px;
  line-height: 1.55;
  color: var(--cc-text-1);
  margin: 0 0 4px;
  word-break: break-word;
}

.bubble--user .bubble-text {
  font-family: var(--cc-font-display);
  font-style: italic;
  font-weight: 400;
  font-size: 22px;
  line-height: 1.4;
  color: var(--sage-700);
}

.bubble-time {
  font-family: var(--cc-font-mono);
  font-size: 0.78rem;
  color: var(--cc-text-3);
}
</style>
