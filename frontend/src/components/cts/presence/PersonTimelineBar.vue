<template>
  <svg :viewBox="`0 0 ${width} ${height}`" width="100%" :height="height" class="person-timeline-bar">
    <defs>
      <pattern id="inferred-stripe" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--cc-divider-strong)" stroke-width="2" />
      </pattern>
    </defs>

    <g v-for="seg in renderedSegments" :key="seg.segment_id"
       @click="$emit('segment-click', seg.raw)"
       style="cursor: pointer;">
      <rect
        :x="seg.x"
        :y="2"
        :width="seg.w"
        :height="height - 4"
        rx="3"
        :fill="seg.color"
        :opacity="seg.is_inferred ? 0.65 : 0.9"
      />
      <rect v-if="seg.is_inferred"
        :x="seg.x" :y="2"
        :width="seg.w" :height="height - 4"
        rx="3"
        fill="url(#inferred-stripe)"
        opacity="0.5"
      />
      <title>{{ seg.tooltip }}</title>
    </g>
  </svg>
</template>

<script setup>
import { computed } from "vue";
import { useTheme } from "vuetify";

const props = defineProps({
  segments: { type: Array, required: true },
  startTime: { type: String, required: true },
  endTime: { type: String, required: true },
  width: { type: Number, default: 800 },
  height: { type: Number, default: 30 },
});
defineEmits(["segment-click"]);

const theme = useTheme();
const MIN_WIDTH_PX = 4;

function roomColor(roomId) {
  const keys = ["primary", "secondary", "info", "success", "warning", "tertiary"];
  const hash = Math.abs(
    String(roomId).split("").reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0)
  );
  return theme.current.value.colors[keys[hash % keys.length]] ?? "#888";
}

function formatDuration(secs) {
  if (!secs || secs < 0) return "0m";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const renderedSegments = computed(() => {
  const wsMs = new Date(props.startTime).getTime();
  const weMs = new Date(props.endTime).getTime();
  const span = Math.max(weMs - wsMs, 60_000);
  const now = Date.now();

  return props.segments.map((seg) => {
    const s = new Date(seg.entered_at).getTime();
    const e = seg.exited_at ? new Date(seg.exited_at).getTime() : Math.min(now, weMs);
    const x = Math.max(0, ((s - wsMs) / span) * props.width);
    const rawW = ((e - s) / span) * props.width;
    const w = Math.max(rawW, MIN_WIDTH_PX);
    const dwellSec = Math.max(0, (e - s) / 1000);
    return {
      segment_id: seg.segment_id,
      x,
      w,
      color: roomColor(seg.room_id),
      is_inferred: !!seg.is_inferred,
      tooltip: `${seg.room_name}: ${formatDuration(dwellSec)}`,
      raw: seg,
    };
  });
});
</script>
