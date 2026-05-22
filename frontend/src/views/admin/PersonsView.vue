<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Household Members</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">People the system recognizes, with their enrollment and live status.</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" prepend-icon="mdi-refresh" class="mr-2" @click="loadLocations" :loading="locLoading">Refresh</v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">Add Member</v-btn>
    </div>

    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="members">Members</v-tab>
      <v-tab value="locations">Live Locations</v-tab>
    </v-tabs>

    <!-- Members Tab -->
    <v-window v-model="activeTab">
      <v-window-item value="members">
        <v-card class="glass-card">
          <v-data-table
            :headers="memberHeaders"
            :items="members"
            :loading="loading"
            item-value="id"
          >
            <template #item.is_active="{ item }">
              <v-chip :color="item.is_active ? 'success' : 'grey'" size="small">
                {{ item.is_active ? 'Active' : 'Inactive' }}
              </v-chip>
            </template>
            <template #item.is_guest="{ item }">
              <v-chip v-if="item.is_guest" color="info" size="small">Guest</v-chip>
              <span v-else class="text-medium-emphasis">Member</span>
            </template>
            <template #item.enrollment="{ item }">
              <v-chip
                v-if="enrollmentMap[item.id]"
                color="success"
                size="small"
                variant="tonal"
                prepend-icon="mdi-face-recognition"
              >
                {{ enrollmentMap[item.id].embedding_count }} photos
              </v-chip>
              <v-chip v-else size="small" variant="tonal" color="grey">
                Not enrolled
              </v-chip>
            </template>
            <template #item.created_at="{ item }">
              {{ formatDate(item.created_at) }}
            </template>
            <template #item.actions="{ item }">
              <v-btn icon="mdi-account-details" size="small" variant="text" color="primary"
                     title="View Profile" :to="{ name: 'admin-person-profile', params: { id: item.id } }" />
              <v-btn icon="mdi-face-recognition" size="small" variant="text" color="primary"
                     title="Enroll Face" @click="openEnroll(item)" />
              <v-btn icon="mdi-map-marker" size="small" variant="text" color="primary"
                     title="Location & History" @click="openDetail(item)" />
              <v-btn icon="mdi-pencil" size="small" variant="text" color="primary" @click="openEdit(item)" />
              <v-btn icon="mdi-delete" size="small" variant="text" color="error"
                     @click="deleteMember(item.id)" />
            </template>
            <template #no-data>
              <div class="pa-6 text-center">
                <v-card flat>
                  <v-card-text class="text-grey text-h6">No members yet</v-card-text>
                  <v-card-text class="text-grey">Add household members to enable person recognition and tracking.</v-card-text>
                </v-card>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- Locations Tab -->
      <v-window-item value="locations">
        <v-row>
          <v-col cols="12" sm="6" md="4" v-for="loc in locations" :key="loc.person_id">
            <v-card class="pa-4">
              <div class="d-flex align-center mb-2">
                <v-icon color="primary" size="28" class="mr-3">mdi-account-circle</v-icon>
                <div>
                  <div class="font-weight-bold">{{ loc.person_name }}</div>
                  <v-chip :color="statusColor(loc.status)" size="x-small" class="mt-1">
                    {{ loc.status }}
                  </v-chip>
                </div>
              </div>
              <div class="text-body-2 d-flex align-center mt-2" v-if="loc.current_room_name">
                <v-icon size="16" class="mr-1">mdi-map-marker</v-icon>
                {{ loc.current_room_name }}
                <v-chip size="x-small" class="ml-2">{{ Math.round(loc.confidence * 100) }}%</v-chip>
              </div>
              <div class="text-body-2 text-medium-emphasis mt-1" v-if="loc.last_seen_at">
                Last seen: {{ formatTime(loc.last_seen_at) }}
              </div>
              <div class="text-body-2 text-medium-emphasis mt-1" v-if="loc.last_sensor_id">
                Sensor: {{ loc.last_sensor_id }}
              </div>
            </v-card>
          </v-col>
          <v-col v-if="locations.length === 0" cols="12">
            <v-alert type="info" variant="tonal">
              No location data available. Locations are tracked when cameras detect enrolled members.
            </v-alert>
          </v-col>
        </v-row>
      </v-window-item>
    </v-window>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog" max-width="560" scrollable persistent>
      <v-card>
        <DialogHeader
          icon="mdi-account-plus"
          :label="editing ? 'Edit' : 'Create New'"
          :title="editing ? 'Member' : 'Member'"
          @close="dialog = false"
        />
        <v-card-text>
          <v-text-field
            v-model="form.id"
            label="Person ID"
            variant="outlined"
            :disabled="editing"
            hint="Unique identifier (e.g. grandma). Must match enrollment in the face service."
            persistent-hint
            class="mb-3"
          />
          <v-text-field v-model="form.name" label="Display Name" variant="outlined" class="mb-3" />
          <v-switch v-model="form.is_guest" label="Guest (not a permanent member)" color="info" class="mb-1" @update:model-value="onGuestToggle" />
          <v-switch v-model="form.is_active" label="Active" color="primary" v-if="editing" class="mb-2" />

          <v-divider class="my-3" />
          <div class="text-subtitle-2 font-weight-semibold mb-2">CTS Alert Profile</div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            Controls which behavioural signals from the tracking system trigger alerts for this person.
          </div>

          <v-btn-toggle
            v-model="alertProfile"
            mandatory
            density="compact"
            color="primary"
            class="mb-3"
            @update:model-value="onProfileChange"
          >
            <v-btn value="senior" size="small">Senior</v-btn>
            <v-btn value="adult" size="small">Adult</v-btn>
            <v-btn value="guest" size="small">Presence only</v-btn>
            <v-btn value="custom" size="small">Custom</v-btn>
          </v-btn-toggle>

          <div class="text-body-2 text-medium-emphasis mb-3">
            <span v-if="alertProfile === 'senior'">All 7 signal types enabled (dementia monitoring).</span>
            <span v-else-if="alertProfile === 'adult'">Presence and sleep/rest signals only.</span>
            <span v-else-if="alertProfile === 'guest'">Absence alert only.</span>
            <span v-else>Custom signal selection.</span>
          </div>

          <v-expand-transition>
            <div v-if="alertProfile === 'custom'">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-1">PRESENCE</div>
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="absence" label="Absence" density="compact" hide-details class="mb-1" />

              <div class="text-caption font-weight-medium text-medium-emphasis mt-2 mb-1">SLEEP / REST</div>
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="nighttime_movement" label="Nighttime movement" density="compact" hide-details class="mb-1" />
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="stillness_anomaly" label="Stillness anomaly" density="compact" hide-details class="mb-1" />

              <div class="text-caption font-weight-medium text-medium-emphasis mt-2 mb-1">DEMENTIA-SPECIFIC</div>
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="pacing" label="Pacing" density="compact" hide-details class="mb-1" />
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="sundowning_index" label="Sundowning index" density="compact" hide-details class="mb-1" />
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="bathroom_dwell_anomaly" label="Bathroom dwell anomaly" density="compact" hide-details class="mb-1" />
              <v-checkbox v-model="form.cts_alert_config.enabled_kinds" value="room_revisit_rate" label="Room revisit rate" density="compact" hide-details class="mb-2" />
            </div>
          </v-expand-transition>

          <v-select
            v-model="form.cts_alert_config.min_severity"
            :items="severityItems"
            label="Minimum alert severity"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-card-text>
        <DialogFooter
          hint="Persons are recognized by the face identification service for presence and activity tracking."
          :confirm-label="editing ? 'Update' : 'Create'"
          @cancel="dialog = false"
          @confirm="saveMember"
        />
      </v-card>
    </v-dialog>

    <!-- Face Enrollment Dialog -->
    <v-dialog v-model="enrollDialog" max-width="600" scrollable persistent>
      <v-card>
        <DialogHeader
          icon="mdi-face-recognition"
          label="Face Enrollment"
          :title="enrollTarget?.name || 'Enroll Face'"
          @close="enrollDialog = false"
        />
        <v-card-text>
          <!-- Current enrollment status -->
          <v-alert
            v-if="enrollmentMap[enrollTarget?.id]"
            type="success"
            variant="tonal"
            class="mb-4"
            density="compact"
          >
            Currently enrolled with {{ enrollmentMap[enrollTarget?.id].embedding_count }} reference photos.
            Uploading more photos will add to the existing enrollment.
          </v-alert>
          <v-alert v-else type="info" variant="tonal" class="mb-4" density="compact">
            Not yet enrolled. Upload 5-10 reference photos for reliable recognition.
          </v-alert>

          <!-- Best practices -->
          <v-expansion-panels variant="accordion" class="mb-4">
            <v-expansion-panel title="Photo tips for best results">
              <v-expansion-panel-text>
                <v-list density="compact">
                  <v-list-item prepend-icon="mdi-camera-burst">Capture 5-10 images per person</v-list-item>
                  <v-list-item prepend-icon="mdi-white-balance-sunny">Vary lighting: daylight, evening lamp, nightlight</v-list-item>
                  <v-list-item prepend-icon="mdi-rotate-3d-variant">Vary angle: front face, slight left/right turns</v-list-item>
                  <v-list-item prepend-icon="mdi-glasses">Include accessories: with/without glasses</v-list-item>
                  <v-list-item prepend-icon="mdi-cctv">Use actual deployment cameras for best domain match</v-list-item>
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>

          <!-- File upload -->
          <v-file-input
            v-model="enrollFiles"
            label="Select photos"
            variant="outlined"
            accept="image/*"
            multiple
            show-size
            prepend-icon="mdi-camera"
            :hint="`${enrollFiles.length} photo(s) selected`"
            persistent-hint
            class="mb-4"
          />

          <!-- Preview thumbnails -->
          <div v-if="enrollPreviews.length" class="d-flex flex-wrap ga-2 mb-4">
            <v-img
              v-for="(src, idx) in enrollPreviews"
              :key="idx"
              :src="src"
              width="80"
              height="80"
              class="rounded-lg border"
            />
          </div>

          <!-- Upload result -->
          <v-alert
            v-if="enrollResult"
            :type="enrollResult.failed_images?.length ? 'warning' : 'success'"
            variant="tonal"
            class="mb-2"
            density="compact"
          >
            Enrolled {{ enrollResult.embedding_count }} embeddings.
            <span v-if="enrollResult.failed_images?.length">
              {{ enrollResult.failed_images.length }} image(s) failed (no face detected).
            </span>
          </v-alert>
        </v-card-text>
        <DialogFooter
          hint="Upload 5–10 reference photos for reliable face recognition."
          cancel-label="Close"
          confirm-label="Upload & Enroll"
          :confirm-loading="enrolling"
          :confirm-disabled="enrollFiles.length === 0"
          @cancel="enrollDialog = false"
          @confirm="submitEnrollment"
        >
          <template #actions>
            <v-btn
              v-if="enrollmentMap[enrollTarget?.id]"
              color="error"
              variant="text"
              @click="unenroll"
            >
              Remove Enrollment
            </v-btn>
          </template>
        </DialogFooter>
      </v-card>
    </v-dialog>

    <!-- Detail Drawer: Location History + Sightings -->
    <v-navigation-drawer v-model="detailDrawer" location="right" temporary width="500" class="cc-drawer-right">
      <v-card flat class="h-100 d-flex flex-column">
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2">mdi-account-circle</v-icon>
          {{ detailMember?.name || 'Details' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailDrawer = false" />
        </v-card-title>

        <!-- Current Location -->
        <v-card-text v-if="detailLocation" class="pb-0">
          <v-alert variant="tonal" :color="statusColor(detailLocation.status)" density="compact" class="mb-3">
            <div class="d-flex align-center">
              <v-icon size="20" class="mr-2">mdi-map-marker</v-icon>
              <strong>{{ detailLocation.current_room_name || 'Unknown' }}</strong>
              <v-chip size="x-small" class="ml-2">{{ detailLocation.status }}</v-chip>
            </div>
            <div class="text-body-2 mt-1" v-if="detailLocation.last_seen_at">
              Last seen: {{ formatTime(detailLocation.last_seen_at) }}
            </div>
          </v-alert>
        </v-card-text>

        <v-tabs v-model="detailTab" color="primary" density="compact" class="px-4">
          <v-tab value="history">Location History</v-tab>
          <v-tab value="sightings">Sightings</v-tab>
        </v-tabs>

        <v-window v-model="detailTab" class="flex-grow-1 detail-window">
          <!-- Location History -->
          <v-window-item value="history" class="h-100 overflow-y-auto">
            <v-card-text>
              <div class="d-flex align-center mb-3">
                <v-select
                  v-model="historyHours"
                  :items="[6, 12, 24, 48, 72]"
                  label="Hours"
                  variant="outlined"
                  density="compact"
                  hide-details
                  style="max-width: 120px"
                />
                <v-btn variant="text" icon="mdi-refresh" size="small" class="ml-2"
                       @click="loadHistory" :loading="histLoading" />
              </div>
              <v-timeline density="compact" side="end" v-if="history.length">
                <v-timeline-item
                  v-for="h in history"
                  :key="h.id"
                  :dot-color="h.exited_at ? 'grey' : 'success'"
                  size="small"
                >
                  <div class="font-weight-medium">{{ h.room_name || 'Unknown' }}</div>
                  <div class="text-body-2 text-medium-emphasis">
                    {{ formatTime(h.entered_at) }}
                    <span v-if="h.exited_at"> → {{ formatTime(h.exited_at) }}</span>
                    <span v-else> (current)</span>
                  </div>
                  <v-chip size="x-small" class="mt-1">{{ h.source }}</v-chip>
                </v-timeline-item>
              </v-timeline>
              <div v-else class="text-medium-emphasis text-center py-4">
                No location history available
              </div>
            </v-card-text>
          </v-window-item>

          <!-- Sightings -->
          <v-window-item value="sightings" class="h-100 overflow-y-auto">
            <v-card-text>
              <v-list density="compact" v-if="sightings.length">
                <v-list-item v-for="s in sightings" :key="s.id" class="px-0">
                  <template #prepend>
                    <v-icon size="20" :color="s.source === 'camera' ? 'primary' : 'info'" class="mr-2">
                      {{ s.source === 'camera' ? 'mdi-cctv' : 'mdi-motion-sensor' }}
                    </v-icon>
                  </template>
                  <v-list-item-title class="text-body-2">
                    {{ s.room_name || 'Unknown' }}
                    <v-chip size="x-small" class="ml-1">{{ Math.round(s.confidence * 100) }}%</v-chip>
                    <v-chip v-if="s.direction" size="x-small" color="info" class="ml-1">
                      {{ directionLabel(s.direction) }}
                    </v-chip>
                  </v-list-item-title>
                  <v-list-item-subtitle>
                    {{ formatTime(s.timestamp) }} · {{ s.sensor_id }}
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
              <div v-else class="text-medium-emphasis text-center py-4">
                No sightings recorded
              </div>
            </v-card-text>
          </v-window-item>
        </v-window>
      </v-card>
    </v-navigation-drawer>
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>

    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" @click="onConfirm">Confirm</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import { formatDateOnly, formatDateTimeShort, DATETIME_COLUMN_WIDTH } from "../../services/timezone.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

// -- Signal kind presets (mirrors backend signal_config.py) --
const SIGNAL_PROFILES = {
  senior: ["pacing", "room_revisit_rate", "bathroom_dwell_anomaly", "sundowning_index", "nighttime_movement", "stillness_anomaly", "absence"],
  adult: ["absence", "nighttime_movement", "stillness_anomaly"],
  guest: ["absence"],
};

const severityItems = [
  { title: "Info (all)", value: "info" },
  { title: "Warning and above", value: "warning" },
  { title: "Emergency only", value: "emergency" },
];

// -- Members list --
const members = ref([]);
const loading = ref(false);
const dialog = ref(false);
const editing = ref(false);
const editId = ref(null);
const activeTab = ref("members");
const alertProfile = ref("senior");

const emptyForm = () => ({
  id: "",
  name: "",
  is_guest: false,
  is_active: true,
  cts_alert_config: { enabled_kinds: [...SIGNAL_PROFILES.senior], min_severity: "info" },
});
const form = ref(emptyForm());

const memberHeaders = [
  { title: "ID", key: "id" },
  { title: "Name", key: "name" },
  { title: "Status", key: "is_active" },
  { title: "Type", key: "is_guest" },
  { title: "Enrollment", key: "enrollment", sortable: false },
  { title: "Added", key: "created_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Actions", key: "actions", sortable: false },
];

// -- Enrollment state --
const enrollmentMap = ref({});
const enrollDialog = ref(false);
const enrollTarget = ref(null);
const enrollFiles = ref([]);
const enrollPreviews = computed(() =>
  enrollFiles.value.map((f) => URL.createObjectURL(f))
);
const enrolling = ref(false);
const enrollResult = ref(null);

async function loadEnrollment() {
  try {
    const data = await api.getEnrolledPersons();
    const map = {};
    for (const m of (data.members || data || [])) {
      map[m.person_id] = m;
    }
    enrollmentMap.value = map;
  } catch {
    // Person-ID service may not be running
    enrollmentMap.value = {};
  }
}

function openEnroll(member) {
  enrollTarget.value = member;
  enrollFiles.value = [];
  enrollResult.value = null;
  enrollDialog.value = true;
}

async function submitEnrollment() {
  if (!enrollTarget.value || enrollFiles.value.length === 0) return;
  enrolling.value = true;
  enrollResult.value = null;
  try {
    const formData = new FormData();
    formData.append("name", enrollTarget.value.name);
    for (const file of enrollFiles.value) {
      formData.append("files", file);
    }
    enrollResult.value = await api.enrollPerson(enrollTarget.value.id, formData);
    await loadEnrollment();
    notify("Face enrollment successful");
  } catch (e) {
    notify(e.message, "error");
  }
  enrolling.value = false;
}

async function unenroll() {
  if (!enrollTarget.value) return;
  if (!await showConfirm("Remove Enrollment", `Remove face enrollment data for "${enrollTarget.value.name}"? They will no longer be recognized by cameras.`))
    return;
  try {
    await api.deleteEnrollment(enrollTarget.value.id);
    await loadEnrollment();
    enrollDialog.value = false;
    notify("Enrollment removed");
  } catch (e) {
    notify(e.message, "error");
  }
}

async function loadMembers() {
  loading.value = true;
  try {
    members.value = await api.getPersons();
  } catch (e) {
    console.error("Failed to load members:", e);
    members.value = [];
  }
  loading.value = false;
}

function _profileFromConfig(config) {
  if (!config || !config.enabled_kinds) return "senior";
  const kinds = new Set(config.enabled_kinds);
  if (kinds.size === SIGNAL_PROFILES.senior.length && SIGNAL_PROFILES.senior.every(k => kinds.has(k))) return "senior";
  if (kinds.size === SIGNAL_PROFILES.adult.length && SIGNAL_PROFILES.adult.every(k => kinds.has(k))) return "adult";
  if (kinds.size === SIGNAL_PROFILES.guest.length && SIGNAL_PROFILES.guest.every(k => kinds.has(k))) return "guest";
  return "custom";
}

function onProfileChange(profile) {
  if (profile !== "custom") {
    form.value.cts_alert_config.enabled_kinds = [...(SIGNAL_PROFILES[profile] || SIGNAL_PROFILES.senior)];
  }
}

function onGuestToggle(isGuest) {
  if (isGuest && alertProfile.value === "senior") {
    alertProfile.value = "adult";
    onProfileChange("adult");
  }
}

function openCreate() {
  form.value = emptyForm();
  alertProfile.value = "senior";
  editing.value = false;
  dialog.value = true;
}

function openEdit(item) {
  const cfg = item.cts_alert_config
    ? { ...item.cts_alert_config, enabled_kinds: [...(item.cts_alert_config.enabled_kinds || [])] }
    : { enabled_kinds: [...SIGNAL_PROFILES.senior], min_severity: "info" };
  form.value = {
    id: item.id,
    name: item.name,
    is_guest: item.is_guest,
    is_active: item.is_active,
    cts_alert_config: cfg,
  };
  alertProfile.value = _profileFromConfig(cfg);
  editId.value = item.id;
  editing.value = true;
  dialog.value = true;
}

async function saveMember() {
  try {
    if (editing.value) {
      const { id, ...update } = form.value;
      await api.updatePerson(editId.value, update);
    } else {
      await api.createPerson(form.value);
    }
    dialog.value = false;
    await loadMembers();
  } catch (e) {
    notify(e.message, "error");
  }
}

async function deleteMember(id) {
  if (!await showConfirm("Delete Member", `Delete member "${id}"? This will remove all their sightings and location data.`))
    return;
  try {
    await api.deletePerson(id);
    await loadMembers();
  } catch (e) {
    notify(e.message, "error");
  }
}

// -- Locations tab --
const locations = ref([]);
const locLoading = ref(false);

async function loadLocations() {
  locLoading.value = true;
  try {
    locations.value = await api.getPersonLocations();
  } catch (e) {
    console.error("Failed to load locations:", e);
    locations.value = [];
  }
  locLoading.value = false;
}

// -- Detail drawer --
const detailDrawer = ref(false);
const detailMember = ref(null);
const detailLocation = ref(null);
const detailTab = ref("history");
const history = ref([]);
const sightings = ref([]);
const historyHours = ref(24);
const histLoading = ref(false);

async function openDetail(member) {
  detailMember.value = member;
  detailDrawer.value = true;
  detailTab.value = "history";

  // Load location, history, sightings in parallel
  const [loc, hist, sight] = await Promise.all([
    api.getPersonLocation(member.id).catch(() => null),
    api.getPersonHistory(member.id, historyHours.value).catch(() => []),
    api.getPersonSightings(member.id, 30).catch(() => []),
  ]);
  detailLocation.value = loc;
  history.value = Array.isArray(hist) ? hist : [];
  sightings.value = Array.isArray(sight) ? sight : [];
}

async function loadHistory() {
  if (!detailMember.value) return;
  histLoading.value = true;
  try {
    history.value = await api.getPersonHistory(detailMember.value.id, historyHours.value);
  } catch (e) {
    console.error("Failed to load history:", e);
    history.value = [];
  }
  histLoading.value = false;
}

watch(historyHours, loadHistory);

// -- Helpers --
const formatDate = formatDateOnly;
const formatTime = formatDateTimeShort;

function statusColor(status) {
  const map = { home: "success", away: "warning", unknown: "grey", sleeping: "info" };
  return map[status] || "grey";
}

function directionLabel(dir) {
  const map = {
    "left-to-right": "→",
    "right-to-left": "←",
    "towards-camera": "↙ approaching",
    "away-from-camera": "↗ leaving",
    "stationary": "● still",
  };
  return map[dir] || dir;
}

// -- Init --
onMounted(() => {
  loadMembers();
  loadLocations();
  loadEnrollment();
});
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}

/* Right-side drawer: pin to viewport, clear app bar, independent scroll */
.cc-drawer-right {
  position: fixed !important;
  top: 0 !important;
  bottom: 0 !important;
  height: auto !important;
}
.cc-drawer-right :deep(.v-navigation-drawer__content) {
  flex: 1 1 0;
  min-height: 0;
  padding-top: 64px;
}

/* Allow the tab window to shrink and scroll inside the flex column */
.detail-window {
  min-height: 0;
}
</style>
