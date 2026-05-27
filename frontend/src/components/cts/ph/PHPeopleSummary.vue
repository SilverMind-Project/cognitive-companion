<template>
  <div class="d-flex flex-wrap ga-4">
    <v-card
      v-for="group in identityGroups"
      :key="group.identity_id"
      variant="flat"
      border
      rounded="lg"
      class="pa-4"
      style="min-width: 280px; flex: 1"
    >
      <div class="text-subtitle-2 font-weight-medium mb-2">
        <v-icon
          size="10"
          :color="identityColor(group.identity_id)"
          class="mr-1"
        >mdi-circle</v-icon>
        {{ group.display_name }}
      </div>
      <div class="text-caption text-medium-emphasis">
        {{ group.count }} active PH{{ group.count !== 1 ? 's' : '' }}
      </div>
    </v-card>
    <v-card
      v-if="unidentifiedCount > 0"
      variant="flat"
      border
      rounded="lg"
      class="pa-4"
      style="min-width: 280px; flex: 1"
      color="warning"
    >
      <div class="text-subtitle-2 font-weight-medium mb-2">
        <v-icon size="10" color="warning" class="mr-1">mdi-help-circle</v-icon>
        Unidentified
      </div>
      <div class="text-caption text-medium-emphasis">
        {{ unidentifiedCount }} PH{{ unidentifiedCount !== 1 ? 's' : '' }}
      </div>
    </v-card>
  </div>
</template>

<script>
import { identityColor } from "@/composables/useIdentityColor";

export default {
  name: "PHPeopleSummary",
  props: {
    identityGroups: { type: Array, default: () => [] },
    unidentifiedCount: { type: Number, default: 0 },
  },
  setup() {
    return { identityColor };
  },
};
</script>
