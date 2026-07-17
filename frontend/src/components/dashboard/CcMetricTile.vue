<template>
  <div
    class="stat-card glass-card pa-4 d-flex flex-column"
    :class="{ 'cursor-pointer': !!route }"
    @click="handleClick"
  >
    <div class="d-flex align-center mb-2">
      <div class="text-caption text-medium-emphasis tracking-tight flex-grow-1">
        {{ label }}
      </div>
      <v-icon v-if="statusIcon" :icon="statusIcon" :color="statusColor" size="16" />
    </div>

    <div class="d-flex align-end ga-2">
      <div class="text-h5 font-weight-bold tracking-tight" :style="{ color: valueColor }">
        {{ value ?? "—" }}
      </div>
      <div v-if="delta != null" class="text-caption mb-1" :class="deltaClass">
        {{ deltaFormatted }}
      </div>
    </div>

    <!-- Sparkline slot for optional mini-chart -->
    <slot name="sparkline" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

const props = defineProps({
  label: {
    type: String,
    required: true,
  },
  /** The primary displayed value. Pass null to show '—'. */
  value: {
    type: [String, Number],
    default: null,
  },
  /** Numeric delta; positive = up, negative = down. */
  delta: {
    type: Number,
    default: null,
  },
  /**
   * Status drives the icon and value color:
   * 'ok' | 'warning' | 'error' | 'info' | null
   */
  status: {
    type: String,
    default: null,
    validator: (v) => [null, "ok", "warning", "error", "info"].includes(v),
  },
  /** vue-router named route or path for click-through navigation. */
  route: {
    type: [String, Object],
    default: null,
  },
});

const router = useRouter();

const STATUS_MAP = {
  ok: { icon: "mdi-check-circle", color: "success" },
  warning: { icon: "mdi-alert", color: "warning" },
  error: { icon: "mdi-alert-circle", color: "error" },
  info: { icon: "mdi-information", color: "info" },
};

const statusIcon = computed(() => STATUS_MAP[props.status]?.icon ?? null);
const statusColor = computed(() => STATUS_MAP[props.status]?.color ?? null);
const valueColor = computed(() =>
  props.status === "error"
    ? "var(--cc-error)"
    : props.status === "warning"
      ? "var(--cc-warning)"
      : "var(--cc-text-1)",
);

const deltaClass = computed(() =>
  props.delta > 0 ? "text-success" : props.delta < 0 ? "text-error" : "text-medium-emphasis",
);
const deltaFormatted = computed(() => {
  if (props.delta == null) return "";
  const sign = props.delta > 0 ? "+" : "";
  return `${sign}${props.delta}`;
});

function handleClick() {
  if (!props.route) return;
  router.push(props.route);
}

defineExpose({ statusIcon, statusColor, deltaClass });
</script>
