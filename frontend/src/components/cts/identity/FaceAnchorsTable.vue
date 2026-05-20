<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-face-recognition</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Recent Face Anchors</span>
    </div>
    <div v-if="anchors.length">
      <div
        v-for="fa in anchors"
        :key="fa.anchor_id || fa.person_id + '-' + fa.time"
        class="d-flex align-center ga-2 py-1"
      >
        <v-icon size="14" :color="fa.confidence > 0.7 ? 'success' : 'warning'">
          mdi-check-circle
        </v-icon>
        <span class="text-caption">{{ identityName(fa.person_id || fa.identity_id) }}</span>
        <v-chip size="x-small" variant="tonal" :color="fa.confidence > 0.7 ? 'success' : 'warning'">
          {{ ((fa.confidence || 0) * 100).toFixed(0) }}%
        </v-chip>
      </div>
    </div>
    <span v-else class="text-caption text-medium-emphasis">No recent face anchors</span>
  </div>
</template>

<script>
export default {
  name: "FaceAnchorsTable",
  props: {
    anchors: { type: Array, default: () => [] },
    identities: { type: Array, default: () => [] },
  },
  computed: {
    identityMap() {
      const m = {};
      for (const id of this.identities) m[id.identity_id] = id.display_name || id.identity_id;
      return m;
    },
  },
  methods: {
    identityName(id) {
      if (!id) return "—";
      return this.identityMap[id] || id.slice(0, 8) + "…";
    },
  },
};
</script>
