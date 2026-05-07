<template>
  <div>
    <v-tabs v-model="activeTab" bg-color="surface" class="mb-4">
      <v-tab value="queries">Knowledge Queries</v-tab>
      <v-tab value="sessions">Quiz Sessions</v-tab>
      <v-tab value="deliveries">Info Card Deliveries</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Queries Tab -->
      <v-window-item value="queries">
        <v-card class="pa-2 mb-2">
          <v-row dense align="center">
            <v-col cols="auto">
              <v-text-field
                v-model="queryDateRange.start"
                label="From"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-text-field
                v-model="queryDateRange.end"
                label="To"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-btn size="small" variant="outlined" @click="fetchQueries">Apply</v-btn>
            </v-col>
          </v-row>
        </v-card>

        <v-data-table
          :headers="queryHeaders"
          :items="queries"
          :loading="queriesLoading"
          :items-per-page="15"
        >
          <template #[`item.query_text`]="{ item }">
            {{ truncate(item.query_text, 80) }}
          </template>

          <template #bottom>
            <div v-if="queries.length === 0 && !queriesLoading" class="pa-6 text-center">
              <v-card flat>
                <v-card-text class="text-grey text-h6">No data yet</v-card-text>
                <v-card-text class="text-grey">
                  Knowledge queries will appear here once seniors begin interacting with the system (Phase 2-3).
                </v-card-text>
              </v-card>
            </div>
          </template>
        </v-data-table>
      </v-window-item>

      <!-- Quiz Sessions Tab -->
      <v-window-item value="sessions">
        <v-card class="pa-2 mb-2">
          <v-row dense align="center">
            <v-col cols="auto">
              <v-text-field
                v-model="sessionDateRange.start"
                label="From"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-text-field
                v-model="sessionDateRange.end"
                label="To"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-btn size="small" variant="outlined" @click="fetchSessions">Apply</v-btn>
            </v-col>
          </v-row>
        </v-card>

        <v-data-table
          :headers="sessionHeaders"
          :items="sessions"
          :loading="sessionsLoading"
          :items-per-page="15"
          :show-expand="true"
          item-value="id"
          @click:row="toggleSessionExpand"
        >
          <template #expanded-row="{ item }">
            <td :colspan="sessionHeaders.length" class="pa-4">
              <v-progress-circular
                v-if="loadingSessionDetail === item.id"
                indeterminate
                size="20"
              />
              <div v-else-if="item._details">
                <div v-for="resp in item._details.responses || []" :key="resp.id" class="mb-3">
                  <v-card variant="outlined" class="pa-2">
                    <div><strong>Q:</strong> {{ resp.question_text }}</div>
                    <div><strong>A:</strong> {{ resp.answer }}</div>
                    <div>
                      <v-chip
                        :color="resp.is_correct ? 'green' : 'red'"
                        size="x-small"
                      >
                        {{ resp.is_correct ? "Correct" : "Incorrect" }}
                      </v-chip>
                      <span class="ml-2 text-caption text-grey">
                        {{ resp.timing_ms ? resp.timing_ms + "ms" : "" }}
                      </span>
                    </div>
                  </v-card>
                </div>
                <div v-if="!item._details.responses?.length" class="text-grey">
                  No responses recorded.
                </div>
              </div>
              <div v-else class="text-grey">
                No detail loaded.
              </div>
            </td>
          </template>

          <template #bottom>
            <div v-if="sessions.length === 0 && !sessionsLoading" class="pa-6 text-center">
              <v-card flat>
                <v-card-text class="text-grey text-h6">No data yet</v-card-text>
                <v-card-text class="text-grey">
                  Quiz sessions will appear here once seniors begin taking quizzes (Phase 2-3).
                </v-card-text>
              </v-card>
            </div>
          </template>
        </v-data-table>
      </v-window-item>

      <!-- Deliveries Tab -->
      <v-window-item value="deliveries">
        <v-card class="pa-2 mb-2">
          <v-row dense align="center">
            <v-col cols="auto">
              <v-text-field
                v-model="deliveryDateRange.start"
                label="From"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-text-field
                v-model="deliveryDateRange.end"
                label="To"
                type="date"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-btn size="small" variant="outlined" @click="fetchDeliveries">Apply</v-btn>
            </v-col>
          </v-row>
        </v-card>

        <v-data-table
          :headers="deliveryHeaders"
          :items="deliveries"
          :loading="deliveriesLoading"
          :items-per-page="15"
        >
          <template #bottom>
            <div v-if="deliveries.length === 0 && !deliveriesLoading" class="pa-6 text-center">
              <v-card flat>
                <v-card-text class="text-grey text-h6">No data yet</v-card-text>
                <v-card-text class="text-grey">
                  Info card deliveries will appear here once the delivery engine is active (Phase 2-3).
                </v-card-text>
              </v-card>
            </div>
          </template>
        </v-data-table>
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";
import { formatDateTime } from "@/services/timezone.js";

const notify = useNotify();

const activeTab = ref("queries");

// --- Queries ---
const queries = ref([]);
const queriesLoading = ref(false);
const queryHeaders = [
  { title: "Asked At", key: "asked_at", sortable: true },
  { title: "Senior ID", key: "senior_id", sortable: true },
  { title: "Query", key: "query_text", sortable: false },
  { title: "Answered Via", key: "answered_via", sortable: true },
  { title: "Channel", key: "channel", sortable: true },
  { title: "Latency (ms)", key: "latency_ms", sortable: true },
];
const queryDateRange = reactive({ start: "", end: "" });

// --- Sessions ---
const sessions = ref([]);
const sessionsLoading = ref(false);
const loadingSessionDetail = ref(null);
const sessionHeaders = [
  { title: "Started At", key: "started_at", sortable: true },
  { title: "Quiz ID", key: "quiz_id", sortable: true },
  { title: "Senior ID", key: "senior_id", sortable: true },
  { title: "Status", key: "status", sortable: true },
  { title: "Responses", key: "response_count", sortable: false, width: 90 },
];
const sessionDateRange = reactive({ start: "", end: "" });

// --- Deliveries ---
const deliveries = ref([]);
const deliveriesLoading = ref(false);
const deliveryHeaders = [
  { title: "Delivered At", key: "delivered_at", sortable: true },
  { title: "Info Card ID", key: "info_card_id", sortable: true },
  { title: "Channels", key: "channels", sortable: false },
  { title: "Viewed At", key: "viewed_at", sortable: true },
  { title: "Dismissed At", key: "dismissed_at", sortable: true },
  { title: "Dismissed By", key: "dismissed_by", sortable: false },
];
const deliveryDateRange = reactive({ start: "", end: "" });

function truncate(text, len) {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "..." : text;
}

function buildDateParams(range) {
  const params = {};
  if (range.start) params.start_date = range.start;
  if (range.end) params.end_date = range.end;
  return params;
}

// --- Queries ---
async function fetchQueries() {
  queriesLoading.value = true;
  try {
    const params = buildDateParams(queryDateRange);
    const res = await api.getSeniorKnowledgeQueries(params);
    queries.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load queries: " + (err.message || err));
  } finally {
    queriesLoading.value = false;
  }
}

// --- Sessions ---
async function fetchSessions() {
  sessionsLoading.value = true;
  try {
    const params = buildDateParams(sessionDateRange);
    const res = await api.getQuizSessions(params);
    sessions.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load sessions: " + (err.message || err));
  } finally {
    sessionsLoading.value = false;
  }
}

async function toggleSessionExpand(event, { item }) {
  if (item._details) {
    item._details = null;
    return;
  }
  loadingSessionDetail.value = item.id;
  try {
    const res = await api.getQuizSession(item.id);
    item._details = res.data ?? res;
  } catch (err) {
    notify.error("Failed to load session detail: " + (err.message || err));
  } finally {
    loadingSessionDetail.value = null;
  }
}

// --- Deliveries ---
async function fetchDeliveries() {
  deliveriesLoading.value = true;
  try {
    const params = buildDateParams(deliveryDateRange);
    const res = await api.getInfoCardDeliveries(params);
    deliveries.value = res.data ?? res ?? [];
  } catch (err) {
    notify.error("Failed to load deliveries: " + (err.message || err));
  } finally {
    deliveriesLoading.value = false;
  }
}

onMounted(() => {
  fetchQueries();
  fetchSessions();
  fetchDeliveries();
});
</script>
