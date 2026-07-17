<template>
  <v-card class="glass-card">
    <v-card-title v-if="title || $slots.title" class="d-flex align-center">
      <slot name="title">
        <span class="tracking-tight">{{ title }}</span>
      </slot>
      <v-spacer />
      <slot name="actions" />
    </v-card-title>
    <div v-if="subtitle" class="text-body-2 text-medium-emphasis px-4 pb-2 pt-0">
      {{ subtitle }}
    </div>
    <v-card-text>
      <slot />
    </v-card-text>
  </v-card>
</template>

<script setup>
defineProps({
  /** Card heading text. Pass a title slot for richer markup. */
  title: {
    type: String,
    default: null,
  },
  /** Optional subtitle rendered below the title. */
  subtitle: {
    type: String,
    default: null,
  },
});
</script>
