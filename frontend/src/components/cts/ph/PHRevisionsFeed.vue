<template>
  <div>
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <v-alert v-if="error" type="error" density="compact" class="mb-2">{{ error }}</v-alert>
    <v-list v-if="revisions.length" density="compact" lines="two">
      <template v-for="(rev, idx) in revisions" :key="rev.revision_id">
        <v-list-item class="py-2">
          <template #prepend>
            <v-avatar size="32" :color="kindColor(rev.kind)" variant="tonal" class="mr-2">
              <v-icon size="16">{{ kindIcon(rev.kind) }}</v-icon>
            </v-avatar>
          </template>
          <template #title>
            <span class="text-body-2 font-weight-medium">
              {{ rev.previous_identity_id || "UNKNOWN" }}
              <v-icon size="12" class="mx-1">mdi-arrow-right</v-icon>
              {{ rev.new_identity_id || "UNKNOWN" }}
            </span>
          </template>
          <template #subtitle>
            <span class="text-caption text-medium-emphasis">
              {{ formatRelative(rev.applied_at) }} · {{ rev.actor }} · {{ rev.rewritten_rows }} rows
            </span>
          </template>
        </v-list-item>
        <v-divider v-if="idx + 1 < revisions.length" />
      </template>
    </v-list>
    <div v-else-if="!loading" class="text-caption text-medium-emphasis pa-2">
      No revisions recorded.
    </div>
  </div>
</template>

<script>
import { ref, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
import { ctsPh } from "@/services/cts_ph";

export default {
  name: "PHRevisionsFeed",
  props: {
    phId: { type: String, required: true },
    limit: { type: Number, default: 20 },
  },
  setup(props) {
    const revisions = ref([]);
    const loading = ref(false);
    const error = ref("");

    async function fetch() {
      loading.value = true;
      error.value = "";
      try {
        const data = await ctsPh.revisions({ ph_id: props.phId, limit: props.limit });
        revisions.value = data.items || [];
      } catch (err) {
        error.value = String(err.message || err);
      } finally {
        loading.value = false;
      }
    }

    function kindColor(kind) {
      return kind === "auto" ? "info" : kind === "manual_merge" ? "primary" : "warning";
    }

    function kindIcon(kind) {
      return kind === "auto" ? "mdi-robot-outline" : kind === "manual_merge" ? "mdi-merge" : "mdi-account-edit-outline";
    }

    onMounted(() => fetch());
    watch(() => props.phId, () => fetch());

    return { revisions, loading, error, formatRelative, kindColor, kindIcon };
  },
};
</script>
