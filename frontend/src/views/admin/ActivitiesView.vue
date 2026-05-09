<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Person Activities</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">A timeline of detected activities, by person and room.</div>
      </div>
      <v-spacer />
      <v-text-field
        v-model="filter.person_id"
        label="Person ID"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 180px"
        @update:model-value="load"
      />
      <v-text-field
        v-model="filter.activity_type"
        label="Activity Type"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 180px"
        @update:model-value="load"
      />
      <v-text-field
        v-model="filter.room_name"
        label="Room"
        variant="outlined"
        density="compact"
        clearable
        hide-details
        style="max-width: 150px"
        @update:model-value="load"
      />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="load">Refresh</v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="items"
        :loading="loading"
        item-value="id"
      >
        <template #item.detected_at="{ item }">
          {{ formatDateTime(item.detected_at) }}
        </template>
        <template #item.confidence="{ item }">
          {{ (item.confidence * 100).toFixed(0) }}%
        </template>
        <template #item.activity_type="{ item }">
          <v-chip size="small" color="info">{{ item.activity_type }}</v-chip>
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No activities yet</v-card-text>
              <v-card-text class="text-grey">Person activities will appear here as the system detects movement and behavior patterns.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";
import { formatDateTime, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";

const items = ref([]);
const loading = ref(false);
const filter = ref({ person_id: "", activity_type: "", room_name: "" });

const headers = [
  { title: "ID", key: "id", width: 80 },
  { title: "Person", key: "person_id" },
  { title: "Activity", key: "activity_type" },
  { title: "Room", key: "room_name" },
  { title: "Confidence", key: "confidence", width: 100 },
  { title: "Detected At", key: "detected_at", width: DATETIME_COLUMN_WIDTH },
];

async function load() {
  loading.value = true;
  try {
    const params = {};
    if (filter.value.person_id) params.person_id = filter.value.person_id;
    if (filter.value.activity_type) params.activity_type = filter.value.activity_type;
    if (filter.value.room_name) params.room_name = filter.value.room_name;
    items.value = await api.getActivities(params);
  } catch (e) {
    console.error("Failed to load activities:", e);
    items.value = [];
  }
  loading.value = false;
}

onMounted(load);
</script>

