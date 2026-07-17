<template>
  <div ref="backdropRef" class="bbox-tag-popover-backdrop" @click.self="emit('close')">
    <v-card class="bbox-tag-popover glass-card" :style="popoverStyle" elevation="8" @click.stop>
      <v-card-text class="pb-1">
        <v-autocomplete
          ref="autocompleteRef"
          v-model="selectedIdentity"
          :items="identityItems"
          item-title="label"
          item-value="id"
          label="Assign identity"
          density="compact"
          variant="outlined"
          :menu-props="{ maxHeight: 280, attach: backdropRef }"
          hide-details
          clearable
        />
        <v-textarea
          v-model="reason"
          label="Reason (optional)"
          rows="2"
          density="compact"
          variant="outlined"
          hide-details
          class="mt-2"
        />
      </v-card-text>
      <v-card-actions class="pt-0">
        <v-btn size="small" color="error" variant="text" @click="emit('delete')">Remove</v-btn>
        <v-spacer />
        <v-btn size="small" variant="text" @click="emit('close')">Cancel</v-btn>
        <v-btn
          size="small"
          color="primary"
          variant="flat"
          :disabled="!selectedIdentity"
          @click="onConfirm"
          >Tag</v-btn
        >
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  position: { type: Object, required: true },
  identities: { type: Array, default: () => [] },
});

const emit = defineEmits(["tag", "delete", "close"]);

const backdropRef = ref(null);
const selectedIdentity = ref(null);
const reason = ref("");

const identityItems = computed(() =>
  props.identities.map((id) => ({
    id: id.id || id.identity_id,
    label: id.display_name || id.name || id.id || id.identity_id,
  })),
);

const popoverStyle = computed(() => {
  const top = Math.max(8, props.position.top);
  const left = Math.max(8, props.position.left);
  return {
    position: "absolute",
    top: `${top}px`,
    left: `${left}px`,
    width: "300px",
  };
});

function onConfirm() {
  emit("tag", {
    identityId: selectedIdentity.value,
    reason: reason.value || "",
  });
}
</script>

<style scoped>
.bbox-tag-popover-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2501;
}
.bbox-tag-popover {
  max-height: 90vh;
  overflow-y: auto;
}
</style>
