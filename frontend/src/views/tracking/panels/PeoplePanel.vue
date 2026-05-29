<template>
  <div>
    <!-- Provenance strip: current room per person from usePersonPresence (D5) -->
    <div v-if="locations.length" class="d-flex flex-wrap ga-2 mb-4">
      <v-chip
        v-for="loc in locations"
        :key="loc.person_id"
        size="small"
        variant="tonal"
        color="primary"
      >
        <v-icon start size="14">mdi-account</v-icon>
        {{ loc.display_name || loc.person_id }}
        <v-divider vertical class="mx-2" />
        {{ loc.room_name || "Unknown" }}
        <div class="ml-2">
          <CcProvenanceBadge :source="loc.source" :quality="loc.quality" />
        </div>
      </v-chip>
    </div>

    <!-- Full PH management panel re-homed here from CTSPersonHypothesesView -->
    <CTSPersonHypothesesView />
  </div>
</template>

<script setup>
import CcProvenanceBadge from "@/components/dashboard/CcProvenanceBadge.vue";
import CTSPersonHypothesesView from "@/views/admin/CTSPersonHypothesesView.vue";

defineProps({
  locations: { type: Array, default: () => [] },
});
</script>
