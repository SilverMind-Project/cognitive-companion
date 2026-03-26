<template>
  <v-dialog :model-value="visible" max-width="500" persistent>
    <v-card color="error" rounded="xl">
      <v-card-title class="text-h5">
        <v-icon class="mr-2">mdi-alert</v-icon>
        Emergency Alert
      </v-card-title>
      <v-card-text class="text-h6">{{ message }}</v-card-text>
      <v-card-actions>
        <v-btn variant="outlined" @click="$emit('dismiss')">Dismiss</v-btn>
        <v-spacer />
        <v-btn variant="elevated" color="white" @click="$emit('request-assistance')">
          Need Assistance
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  message: { type: String, default: "" },
});

defineEmits(["dismiss", "request-assistance"]);
</script>
