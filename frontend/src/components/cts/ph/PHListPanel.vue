<template>
  <v-list v-if="items.length" density="compact">
    <v-list-item
      v-for="ph in items"
      :key="ph.ph_id"
      class="cursor-pointer"
      @click="$emit('select', ph)"
    >
      <template #prepend>
        <v-icon size="12" :color="identityColor(ph.current_identity_id || '')">mdi-circle</v-icon>
      </template>
      <template #title>
        <span class="text-body-2">{{ ph.identity_display_name || ph.current_identity_id || "UNKNOWN" }}</span>
      </template>
      <template #subtitle>
        <span class="text-caption text-medium-emphasis">
          {{ ph.room_name || "—" }} · {{ formatRelative(ph.last_seen_at) }}
        </span>
      </template>
    </v-list-item>
  </v-list>
  <div v-else class="text-caption text-medium-emphasis pa-2">
    {{ emptyMessage }}
  </div>
</template>

<script>
import { identityColor } from "@/composables/useIdentityColor";
import { formatRelative } from "@/composables/useFormatRelative";

export default {
  name: "PHListPanel",
  props: {
    items: { type: Array, default: () => [] },
    emptyMessage: { type: String, default: "No PHs" },
  },
  emits: ["select"],
  setup() {
    return { identityColor, formatRelative };
  },
};
</script>
