<template>
  <div class="cc-feed-wrapper" :style="{ maxHeight: maxHeight + 'px' }">
    <div v-if="!events.length" class="pa-4 text-center text-medium-emphasis">
      <slot name="empty">No activity yet</slot>
    </div>
    <div
      v-else
      ref="listEl"
      class="cc-feed-list overflow-y-auto"
      :style="{ maxHeight: maxHeight + 'px' }"
    >
      <div
        v-for="event in visibleEvents"
        :key="event.id"
        class="cc-feed-item d-flex align-start ga-3 pa-3"
      >
        <v-icon
          :icon="event.icon || 'mdi-circle-small'"
          :color="event.color || 'primary'"
          size="18"
          class="mt-1"
        />
        <div class="flex-grow-1">
          <div class="text-body-2 font-weight-medium">{{ event.title }}</div>
          <div v-if="event.description" class="text-caption text-medium-emphasis">
            {{ event.description }}
          </div>
        </div>
        <div class="text-caption text-medium-emphasis cc-feed-time">
          {{ formatTimestamp(event.timestamp) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from "vue";
import { formatDateTimeShort } from "@/services/timezone.js";

const props = defineProps({
  /**
   * Feed events (append-only):
   * [{ id: string, timestamp: ISO string, title: string, description?: string,
   *    icon?: string, color?: string }]
   *
   * This component does NOT open its own socket. Pass events as props.
   * Rule 17 / D1: data comes in via props, events go out via emits.
   */
  events: {
    type: Array,
    default: () => [],
  },
  /** Maximum number of most-recent events to render (virtualisation). */
  maxVisible: {
    type: Number,
    default: 100,
  },
  /** CSS pixel height of the scroll container. */
  maxHeight: {
    type: Number,
    default: 360,
  },
});

const listEl = ref(null);

// Only render the last maxVisible events to avoid DOM growth on long-running sessions.
const visibleEvents = computed(() => {
  const arr = props.events;
  if (arr.length <= props.maxVisible) return arr;
  return arr.slice(arr.length - props.maxVisible);
});

function formatTimestamp(t) {
  return formatDateTimeShort(t);
}

// Auto-scroll to bottom when new events arrive.
watch(
  () => props.events.length,
  () => {
    nextTick(() => {
      if (listEl.value) {
        listEl.value.scrollTop = listEl.value.scrollHeight;
      }
    });
  },
);

defineExpose({ visibleEvents, formatTimestamp });
</script>

<style scoped>
.cc-feed-wrapper {
  position: relative;
  width: 100%;
}

.cc-feed-list {
  overscroll-behavior: contain;
}

.cc-feed-item:not(:last-child) {
  border-bottom: 1px solid var(--cc-divider);
}

.cc-feed-time {
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
