<template>
  <div>
    <v-card flat>
      <v-card-title class="d-flex align-center">
        {{ mode === "merge" ? "Merge Identity" : "Correct Identity" }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
      </v-card-title>
      <v-card-text>
        <!-- Loading -->
        <div v-if="loading" class="d-flex justify-center py-4">
          <v-progress-circular indeterminate size="32" color="primary" />
        </div>

        <template v-else>
          <v-alert v-if="error" type="warning" density="compact" class="mb-3">
            {{ error }}
          </v-alert>

          <!-- Track summary -->
          <TrackSummaryHeader :track="trackDetail || track" />

          <!-- Posterior bar -->
          <PosteriorBar :posterior="trackDetail?.posterior || null" />

          <!-- Keyframe strip -->
          <KeyframeStrip :frames="keyframes" @click="$emit('keyframe-click', $event)" />

          <!-- Correction form -->
          <div class="mb-3">
            <v-autocomplete
              v-if="mode === 'merge'"
              v-model="form.from_identity_id"
              :items="identityItems"
              item-title="label"
              item-value="identity_id"
              label="From identity"
              variant="outlined"
              density="compact"
              class="mb-3"
              clearable
            />
            <v-autocomplete
              v-model="form.new_identity_id"
              :items="identityItems"
              item-title="label"
              item-value="identity_id"
              :label="mode === 'merge' ? 'To identity' : 'New identity'"
              variant="outlined"
              density="compact"
              class="mb-3"
              clearable
              :hint="mode === 'correct' ? 'Leave blank to mark as UNKNOWN' : ''"
              persistent-hint
            />
            <v-text-field
              v-model="form.reason"
              label="Reason"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-btn block variant="flat" color="primary" :loading="saving" @click="$emit('apply', form)">
              Apply
            </v-btn>
          </div>

          <v-divider class="mb-3" />

          <!-- Co-occurring tracks -->
          <CoOccurringPanel :tracks="coOccurring" :identities="identities" />

          <!-- Face anchors -->
          <FaceAnchorsTable :anchors="faceAnchors" :identities="identities" />

          <!-- Trail -->
          <TrailMiniMap :points="trailPoints" />
        </template>
      </v-card-text>
    </v-card>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import TrackSummaryHeader from "./TrackSummaryHeader.vue";
import PosteriorBar from "./PosteriorBar.vue";
import KeyframeStrip from "./KeyframeStrip.vue";
import CoOccurringPanel from "./CoOccurringPanel.vue";
import FaceAnchorsTable from "./FaceAnchorsTable.vue";
import TrailMiniMap from "./TrailMiniMap.vue";

export default {
  name: "IdentityInspectorDrawer",
  components: {
    TrackSummaryHeader,
    PosteriorBar,
    KeyframeStrip,
    CoOccurringPanel,
    FaceAnchorsTable,
    TrailMiniMap,
  },
  props: {
    track: { type: Object, required: true },
    mode: { type: String, default: "correct" },
    identities: { type: Array, default: () => [] },
  },
  emits: ["apply", "close", "keyframe-click"],
  data() {
    return {
      loading: false,
      saving: false,
      trackDetail: null,
      keyframes: [],
      coOccurring: [],
      faceAnchors: [],
      trailPoints: [],
      error: "",
      form: {
        from_identity_id: "",
        new_identity_id: "",
        reason: this.mode === "merge" ? "manual_merge" : "manual",
      },
    };
  },
  computed: {
    identityItems() {
      return this.identities.map((id) => ({
        identity_id: id.identity_id,
        label: id.display_name || id.identity_id,
      }));
    },
  },
  watch: {
    track: {
      immediate: true,
      handler() {
        this.resetForm();
        this.loadEnrichment();
      },
    },
  },
  methods: {
    resetForm() {
      this.form = {
        from_identity_id: this.track?.current_identity_id || "",
        new_identity_id: "",
        reason: this.mode === "merge" ? "manual_merge" : "manual",
      };
    },
    async loadEnrichment() {
      this.loading = true;
      this.error = "";
      const id = this.track?.global_track_id;
      if (!id) {
        this.loading = false;
        return;
      }
      const [detail, kf, co, trail] = await Promise.allSettled([
        cts.getGlobalTrackDetail(id),
        cts.getTrackKeyframes(id),
        cts.getCoOccurringTracks(id),
        cts.getTrackTrail(id),
      ]);

      const failures = [detail, kf, co, trail].filter((r) => r.status === "rejected");
      if (failures.length) {
        this.error = `Unable to load ${failures.length} enrichment section${failures.length === 1 ? "" : "s"}.`;
      }
      const detailValue = detail.status === "fulfilled" ? detail.value : null;
      const keyframeValue = kf.status === "fulfilled" ? kf.value : null;
      const coValue = co.status === "fulfilled" ? co.value : null;
      const trailValue = trail.status === "fulfilled" ? trail.value : null;

      this.trackDetail = detailValue || this.track;
      this.keyframes = keyframeValue?.keyframes || [];
      this.coOccurring = coValue?.co_occurring || [];
      this.faceAnchors = detailValue?.posterior?.face_anchors || [];
      this.trailPoints = (trailValue?.points || []).flatMap((p) => p.points || [p]);
      this.loading = false;
    },
  },
};
</script>
