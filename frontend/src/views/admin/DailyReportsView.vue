<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Daily Reports</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Wellness summaries and activity breakdowns by person and date.</div>
      </div>
      <v-spacer />
    </div>

    <v-card class="mb-4">
      <v-card-text class="d-flex ga-3 flex-wrap align-end">
        <v-select
          v-model="selectedPerson"
          :items="persons"
          item-value="id"
          item-title="name"
          label="Person"
          variant="outlined"
          density="compact"
          clearable
          style="max-width: 250px"
        />
        <v-checkbox
          v-model="includeRoomTrends"
          label="Include Room Trends"
          density="compact"
          hide-details
        />
      </v-card-text>
    </v-card>

    <v-card v-if="selectedPerson">
      <v-card-text class="pa-6">
        <DailyReportCard
          ref="reportRef"
          :person-id="selectedPerson"
          :include-room-trends="includeRoomTrends"
        />
      </v-card-text>
    </v-card>

    <v-alert v-else type="info" variant="tonal">
      Select a person to view their daily reports.
    </v-alert>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from "vue";
import { api } from "../../services/api.js";
import DailyReportCard from "../../components/person/DailyReportCard.vue";

const persons = ref([]);
const selectedPerson = ref(null);
const includeRoomTrends = ref(false);
const reportRef = ref(null);

async function loadPersons() {
  try {
    const data = await api.getPersons();
    persons.value = data || [];
  } catch (e) {
    console.error("Failed to load persons:", e);
  }
}

watch(selectedPerson, () => {
  if (selectedPerson.value && reportRef.value) {
    reportRef.value.load();
  }
});

onMounted(() => {
  loadPersons();
});
</script>
