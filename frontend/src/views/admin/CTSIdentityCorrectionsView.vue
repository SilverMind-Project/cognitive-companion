<template>
  <div>
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
      <v-btn variant="tonal" prepend-icon="mdi-refresh" @click="loadAll">
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
      <v-col cols="12" md="7">
        <v-card class="glass-card mb-4">
          <v-card-title class="d-flex align-center">
            Active global tracks
            <v-spacer />
            <v-chip size="small" variant="tonal">{{ tracks.length }}</v-chip>
          </v-card-title>
          <v-data-table
            :headers="trackHeaders"
            :items="tracks"
            :loading="loading.tracks"
            density="compact"
          >
            <template #item.current_identity_id="{ item }">
              <v-chip v-if="item.current_identity_id" color="success" size="small">
                {{ item.current_identity_id }}
              </v-chip>
              <v-chip v-else color="warning" size="small">UNKNOWN</v-chip>
            </template>
            <template #item.cameras="{ item }">
              <span class="text-caption">{{ (item.camera_ids || []).join(", ") }}</span>
            </template>
            <template #item.actions="{ item }">
              <v-btn
                size="small"
                variant="tonal"
                prepend-icon="mdi-account-edit"
                @click="openCorrection(item, 'correct')"
              >
                Correct
              </v-btn>
              <v-btn
                size="small"
                variant="outlined"
                class="ml-2"
                prepend-icon="mdi-merge"
                @click="openCorrection(item, 'merge')"
              >
                Merge
              </v-btn>
            </template>
          </v-data-table>
        </v-card>
      </v-col>

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
              >
                <v-list-item-title class="text-body-2">
                  <span class="text-medium-emphasis">{{
                    rev.earliest_entered_at
                  }}</span>
                  &middot; {{ rev.previous_identity_id || "—" }} &rarr; revised
                </v-list-item-title>
                <v-list-item-subtitle>
                  <span class="text-caption">
                    track: {{ rev.global_track_id || "—" }} &middot;
                    {{ rev.rewritten_rows }} rows rewritten
                  </span>
                </v-list-item-subtitle>
              </v-list-item>
              <v-list-item v-if="!revisions.length">
                <v-list-item-title class="text-caption text-medium-emphasis">
                  No revisions in the selected window.
                </v-list-item-title>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="dialogOpen" max-width="560" persistent>
      <v-card>
        <v-card-title>
          {{ dialogMode === "merge" ? "Merge identities" : "Correct identity" }}
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 mb-2">
            GlobalTrack: <strong>{{ form.global_track_id }}</strong>
          </div>
          <div class="text-body-2 mb-4">
            Current identity: {{ form.previous_identity_id || "unknown" }}
          </div>
          <v-text-field
            v-if="dialogMode === 'merge'"
            v-model="form.from_identity_id"
            label="From identity id"
            variant="outlined"
          />
          <v-text-field
            v-model="form.new_identity_id"
            :label="dialogMode === 'merge' ? 'To identity id' : 'New identity id'"
            variant="outlined"
            :placeholder="dialogMode === 'correct' ? 'Leave blank to mark UNKNOWN' : ''"
          />
          <v-text-field
            v-model="form.reason"
            label="Reason"
            variant="outlined"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialogOpen = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="submit">
            Apply
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import { DATETIME_COLUMN_WIDTH } from "@/services/timezone";

export default {
  name: "CTSIdentityCorrectionsView",
  data() {
    return {
      error: "",
      loading: { tracks: false, revisions: false },
      tracks: [],
      revisions: [],
      trackHeaders: [
        { title: "GlobalTrack", key: "global_track_id", sortable: true },
        { title: "Current identity", key: "current_identity_id" },
        { title: "Cameras", key: "cameras", sortable: false },
        { title: "Last seen", key: "last_seen_at", sortable: true, width: DATETIME_COLUMN_WIDTH },
        { title: "", key: "actions", sortable: false, align: "end" },
      ],
      dialogOpen: false,
      dialogMode: "correct",
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
  mounted() {
    this.loadAll();
  },
  methods: {
    async loadAll() {
      await Promise.all([this.loadTracks(), this.loadRevisions()]);
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
    openCorrection(track, mode) {
      this.dialogMode = mode;
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
