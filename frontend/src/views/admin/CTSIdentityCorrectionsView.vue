<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Identity Corrections</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Review and override the identity assigned to each active tracking
          graph. Every override is logged as a revision and flows back into
          the dashboard within ~2 seconds.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading.tracks" @click="loadAll">
        Refresh
      </v-btn>
    </div>

    <v-alert
      v-if="error"
      type="error"
      class="mb-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>

    <v-row>
      <!-- Active tracks card grid -->
      <v-col cols="12" md="7">
        <div class="d-flex align-center mb-3">
          <span class="text-subtitle-1 font-weight-medium">Active global tracks</span>
          <v-chip size="small" variant="tonal" class="ml-2">{{ tracks.length }}</v-chip>
        </div>

        <div v-if="loading.tracks" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <div v-else-if="!tracks.length" class="text-center text-medium-emphasis py-8">
          No active global tracks.
        </div>

        <v-row v-else>
          <v-col
            v-for="track in tracks"
            :key="track.global_track_id"
            cols="12"
            sm="6"
          >
            <v-card class="glass-card track-card" height="100%">
              <!-- Thumbnail -->
              <v-img
                v-if="track.latest_keyframe_minio_key"
                :src="frameUrl(track.latest_keyframe_minio_key)"
                height="140"
                cover
                class="track-thumb"
              >
                <div class="track-thumb-overlay d-flex align-end pa-2">
                  <v-chip
                    size="x-small"
                    :color="track.current_identity_id ? 'success' : 'warning'"
                    variant="flat"
                  >
                    {{ identityLabel(track) }}
                  </v-chip>
                </div>
              </v-img>
              <div
                v-else
                class="track-thumb-placeholder d-flex align-center justify-center flex-column"
              >
                <v-icon size="40" color="medium-emphasis">mdi-account-circle-outline</v-icon>
                <span class="text-caption text-medium-emphasis mt-1">No keyframe yet</span>
              </div>

              <v-card-text class="pb-1 pt-2">
                <!-- Identity name or UNKNOWN badge -->
                <div class="d-flex align-center ga-2 mb-1">
                  <v-chip
                    :color="track.current_identity_id ? 'success' : 'warning'"
                    size="small"
                    variant="tonal"
                  >
                    <v-icon start size="14">mdi-account</v-icon>
                    {{ identityLabel(track) }}
                  </v-chip>
                </div>

                <!-- Track ID (truncated) -->
                <div
                  class="text-caption text-medium-emphasis font-mono text-truncate"
                  :title="track.global_track_id"
                >
                  {{ track.global_track_id }}
                </div>

                <!-- Camera list -->
                <div class="text-caption text-medium-emphasis mt-1 text-truncate">
                  <v-icon size="12" class="mr-1">mdi-cctv</v-icon>
                  {{ (track.camera_ids || []).join(", ") || "—" }}
                </div>

                <!-- Last seen -->
                <div class="text-caption text-medium-emphasis mt-1">
                  <v-icon size="12" class="mr-1">mdi-clock-outline</v-icon>
                  {{ formatRelative(track.last_seen_at) }}
                </div>
              </v-card-text>

              <v-card-actions class="pt-0">
                <v-btn
                  size="small"
                  variant="tonal"
                  prepend-icon="mdi-account-edit"
                  @click="openCorrection(track, 'correct')"
                >
                  Correct
                </v-btn>
                <v-btn
                  size="small"
                  variant="outlined"
                  prepend-icon="mdi-merge"
                  @click="openCorrection(track, 'merge')"
                >
                  Merge
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
      </v-col>

      <!-- Revision audit log -->
      <v-col cols="12" md="5">
        <v-card class="glass-card">
          <v-card-title class="d-flex align-center">
            Revision audit log
            <v-spacer />
            <v-chip size="small" variant="tonal">{{ revisions.length }}</v-chip>
          </v-card-title>
          <v-card-text>
            <v-list density="compact">
              <v-list-item
                v-for="rev in revisions"
                :key="rev.revision_id"
                :subtitle="`track: ${shortId(rev.global_track_id)} · ${rev.rewritten_rows} rows rewritten`"
              >
                <template #title>
                  <span class="text-caption text-medium-emphasis">
                    {{ formatRelative(rev.earliest_entered_at) }}
                  </span>
                  &middot;
                  <span class="font-weight-medium">
                    {{ identityDisplayName(rev.previous_identity_id) }}
                  </span>
                  &rarr; revised
                </template>
              </v-list-item>
              <v-list-item v-if="!revisions.length">
                <template #title>
                  <span class="text-caption text-medium-emphasis">
                    No revisions in the selected window.
                  </span>
                </template>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Correction / Merge dialog -->
    <v-dialog v-model="dialogOpen" max-width="560" persistent>
      <v-card>
        <DialogHeader
          :icon="dialogMode === 'merge' ? 'mdi-merge' : 'mdi-account-edit'"
          :label="dialogMode === 'merge' ? 'Merge' : 'Correct'"
          :title="dialogMode === 'merge' ? 'Merge identity' : 'Correct identity'"
          @close="dialogOpen = false"
        />
        <v-card-text>
          <!-- Track thumbnail preview -->
          <div v-if="dialogTrack" class="d-flex align-center ga-3 mb-4">
            <v-img
              v-if="dialogTrack.latest_keyframe_minio_key"
              :src="frameUrl(dialogTrack.latest_keyframe_minio_key)"
              width="72"
              height="72"
              cover
              rounded="lg"
            />
            <v-icon v-else size="48" color="medium-emphasis">mdi-account-circle-outline</v-icon>
            <div>
              <div class="text-body-2 font-weight-medium">
                Current: {{ identityLabel(dialogTrack) }}
              </div>
              <div
                class="text-caption text-medium-emphasis font-mono"
                :title="form.global_track_id"
              >
                {{ form.global_track_id }}
              </div>
            </div>
          </div>

          <!-- Merge: source identity field -->
          <v-autocomplete
            v-if="dialogMode === 'merge'"
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

          <!-- Target identity picker -->
          <v-autocomplete
            v-model="form.new_identity_id"
            :items="identityItems"
            item-title="label"
            item-value="identity_id"
            :label="dialogMode === 'merge' ? 'To identity' : 'New identity'"
            variant="outlined"
            density="compact"
            class="mb-3"
            clearable
            :placeholder="dialogMode === 'correct' ? 'Leave blank to mark UNKNOWN' : ''"
            :hint="dialogMode === 'correct' ? 'Select a known person or leave blank to set UNKNOWN' : ''"
            persistent-hint
          />

          <v-text-field
            v-model="form.reason"
            label="Reason"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <DialogFooter
          hint="Manual identity corrections help train the tracking system for better future matches."
          confirm-label="Apply"
          :confirm-loading="saving"
          @cancel="dialogOpen = false"
          @confirm="submit"
        />
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import { formatRelative } from "@/composables/useFormatRelative";
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

export default {
  name: "CTSIdentityCorrectionsView",
  components: { DialogHeader, DialogFooter },
  data() {
    return {
      error: "",
      loading: { tracks: false, revisions: false },
      tracks: [],
      revisions: [],
      identities: [],
      dialogOpen: false,
      dialogMode: "correct",
      dialogTrack: null,
      saving: false,
      form: {
        global_track_id: "",
        previous_identity_id: "",
        from_identity_id: "",
        new_identity_id: "",
        reason: "manual",
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
    identityMap() {
      const m = {};
      for (const id of this.identities) {
        m[id.identity_id] = id.display_name || id.identity_id;
      }
      return m;
    },
  },
  mounted() {
    this.loadAll();
  },
  methods: {
    formatRelative,
    frameUrl(minioKey) {
      if (!minioKey) return null;
      const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
      const apiKey = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encodedKey}?api_key=${apiKey}`;
    },
    identityLabel(track) {
      if (!track.current_identity_id) return "UNKNOWN";
      return this.identityMap[track.current_identity_id] || track.current_identity_id;
    },
    identityDisplayName(identityId) {
      if (!identityId) return "—";
      return this.identityMap[identityId] || identityId;
    },
    shortId(id) {
      if (!id) return "—";
      return id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
    },
    async loadAll() {
      await Promise.all([this.loadTracks(), this.loadRevisions(), this.loadIdentities()]);
    },
    async loadTracks() {
      this.loading.tracks = true;
      try {
        const data = await cts.getGlobalTracks(true);
        this.tracks = data.tracks || [];
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loading.tracks = false;
      }
    },
    async loadRevisions() {
      this.loading.revisions = true;
      try {
        const data = await cts.getRevisions({ window_hours: 48, limit: 50 });
        this.revisions = data.revisions || [];
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loading.revisions = false;
      }
    },
    async loadIdentities() {
      try {
        const data = await cts.getIdentities();
        this.identities = data.identities || [];
      } catch {
        // Non-critical: identity names degrade to raw IDs.
      }
    },
    openCorrection(track, mode) {
      this.dialogMode = mode;
      this.dialogTrack = track;
      this.form = {
        global_track_id: track.global_track_id,
        previous_identity_id: track.current_identity_id || "",
        from_identity_id: track.current_identity_id || "",
        new_identity_id: "",
        reason: mode === "merge" ? "manual_merge" : "manual",
      };
      this.dialogOpen = true;
    },
    async submit() {
      this.saving = true;
      try {
        if (this.dialogMode === "merge") {
          await cts.mergeIdentities({
            global_track_id: this.form.global_track_id,
            from_identity_id: this.form.from_identity_id,
            to_identity_id: this.form.new_identity_id,
            reason: this.form.reason,
          });
        } else {
          await cts.applyCorrection({
            global_track_id: this.form.global_track_id,
            new_identity_id: this.form.new_identity_id || null,
            reason: this.form.reason,
          });
        }
        this.dialogOpen = false;
        await this.loadAll();
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style scoped>
.track-card {
  transition: box-shadow 0.2s;
}
.track-card:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}
.track-thumb {
  border-radius: 12px 12px 0 0;
}
.track-thumb-overlay {
  background: linear-gradient(to top, rgba(0, 0, 0, 0.55), transparent);
  height: 100%;
}
.track-thumb-placeholder {
  height: 140px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 12px 12px 0 0;
}
.font-mono {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}
</style>
