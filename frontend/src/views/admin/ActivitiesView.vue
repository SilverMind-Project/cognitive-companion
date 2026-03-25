<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h2 class="text-h5">Person Activities</h2>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" @click="load" />
    </div>

    <v-card rounded="xl" class="mb-4">
      <v-card-text class="d-flex ga-3 flex-wrap">
        <v-text-field
          v-model="filter.person_id"
          label="Person ID"
          variant="outlined"
          density="compact"
          clearable
          style="max-width: 200px"
          @update:model-value="load"
        />
        <v-text-field
          v-model="filter.activity_type"
          label="Activity Type"
          variant="outlined"
          density="compact"
          clearable
          style="max-width: 200px"
          @update:model-value="load"
        />
        <v-text-field
          v-model="filter.room_name"
          label="Room"
          variant="outlined"
          density="compact"
          clearable
          style="max-width: 200px"
          @update:model-value="load"
        />
      </v-card-text>
    </v-card>

    <v-card rounded="xl">
      <v-data-table
        :headers="headers"
        :items="items"
        :loading="loading"
        item-value="id"
      >
        <template #item.detected_at="{ item }">
          {{ formatDate(item.detected_at) }}
        </template>
        <template #item.confidence="{ item }">
          {{ (item.confidence * 100).toFixed(0) }}%
        </template>
        <template #item.activity_type="{ item }">
          <v-chip size="small" color="info">{{ item.activity_type }}</v-chip>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../../services/api.js";

const items = ref([]);
const loading = ref(false);
const filter = ref({ person_id: "", activity_type: "", room_name: "" });

const headers = [
  { title: "ID", key: "id", width: 80 },
  { title: "Person", key: "person_id" },
  { title: "Activity", key: "activity_type" },
  { title: "Room", key: "room_name" },
  { title: "Confidence", key: "confidence", width: 100 },
  { title: "Detected At", key: "detected_at" },
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

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "";
}

onMounted(load);
</script>
