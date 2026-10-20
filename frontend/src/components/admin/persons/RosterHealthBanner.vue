<template>
  <v-alert
    v-if="health && !health.is_complete"
    type="warning"
    variant="tonal"
    class="mb-4"
    data-testid="roster-health-banner"
  >
    <div class="font-weight-medium">Some people may be recognized as someone else.</div>
    <div class="text-body-2 mt-1">
      Cameras match every face to the closest enrolled person, so people who come regularly but are
      not enrolled can be mistaken for an enrolled family member.
    </div>
    <ul class="text-body-2 mt-2 pl-4">
      <li v-if="health.members_without_face_enrollment.length" data-testid="roster-missing">
        Needs at least {{ health.min_face_embeddings }} enrollment photos: {{ missingSummary }}. Use
        Enroll in the Members table below.
      </li>
      <li v-if="health.surfaced_unnamed_visitor_clusters > 0" data-testid="roster-visitors">
        {{ health.surfaced_unnamed_visitor_clusters }} recurring
        {{ health.surfaced_unnamed_visitor_clusters === 1 ? "visitor is" : "visitors are" }}
        waiting to be named or dismissed in
        <router-link to="/admin/visitors" class="text-primary">Visitors</router-link>.
      </li>
    </ul>
  </v-alert>
  <v-alert
    v-else-if="error"
    type="info"
    variant="tonal"
    density="compact"
    class="mb-4"
    data-testid="roster-health-error"
  >
    Enrollment check unavailable: {{ error }}
  </v-alert>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getRosterHealth, type RosterHealthEnvelope } from "@/services/modules/persons";

const health = ref<RosterHealthEnvelope | null>(null);
const error = ref("");

const missingSummary = computed(() =>
  (health.value?.members_without_face_enrollment ?? [])
    .map((m) => `${m.name} (${m.embedding_count})`)
    .join(", "),
);

async function refresh(): Promise<void> {
  try {
    health.value = await getRosterHealth();
    error.value = "";
  } catch (e) {
    health.value = null;
    error.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(refresh);

defineExpose({ refresh });
</script>
