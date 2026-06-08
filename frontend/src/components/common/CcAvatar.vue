<script setup>
/**
 * CcAvatar — represents a person (the senior or a caregiver). Shows a photo when
 * available, otherwise warm initials on a calm color picked from the name. An
 * optional wellbeing ring mirrors CcStatusPill semantics.
 *
 *   <CcAvatar name="Ruth Alvarez" size="lg" status="steady" />
 *   <CcAvatar name="Dana" :src="photoUrl" />
 *
 * Sizes: xs | sm | md | lg | xl. status: steady | notice | alert.
 * For decorative icon containers, use a plain v-avatar instead — this component
 * is specifically for people.
 */
import { computed } from "vue";

const props = defineProps({
  name: { type: String, default: "" },
  src: { type: String, default: null },
  size: { type: String, default: "md" }, // xs | sm | md | lg | xl
  status: { type: String, default: null }, // steady | notice | alert
});

const SIZES = { xs: 30, sm: 38, md: 48, lg: 64, xl: 88 };
// Calm, on-brand palette — sage, terracotta, info blue.
const PALETTE = ["var(--sage-500)", "var(--terra-400)", "var(--blue-info)", "var(--sage-600)"];
const RINGS = {
  steady: "var(--green-care)",
  notice: "var(--gold-notice)",
  alert: "var(--brick-alert)",
};

const px = computed(() => SIZES[props.size] || SIZES.md);
const initials = computed(() =>
  (props.name || "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] || "")
    .join("")
    .toUpperCase()
);
const bg = computed(() => PALETTE[(props.name.charCodeAt(0) || 0) % PALETTE.length]);
const ring = computed(() => (props.status ? RINGS[props.status] : null));
</script>

<template>
  <span
    class="cc-avatar"
    :style="{
      width: px + 'px',
      height: px + 'px',
      fontSize: px * 0.4 + 'px',
      background: src ? 'var(--stone-200)' : bg,
      boxShadow: ring ? `0 0 0 2px var(--cc-surface), 0 0 0 4px ${ring}` : 'none',
    }"
    :title="name"
  >
    <img v-if="src" :src="src" :alt="name" class="cc-avatar__img" />
    <span v-else class="cc-avatar__initials">{{ initials }}</span>
  </span>
</template>

<style scoped>
.cc-avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  overflow: hidden;
  border-radius: var(--cc-radius-pill);
  color: var(--text-on-brand, #fbf8f3);
  font-family: var(--cc-font);
  font-weight: 700;
  letter-spacing: 0.01em;
  user-select: none;
}
.cc-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cc-avatar__initials {
  line-height: 1;
}
</style>
