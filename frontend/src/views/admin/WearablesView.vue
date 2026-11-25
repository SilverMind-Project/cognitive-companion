<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Wearables & RF Nodes</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Register wearable devices, record consented bindings to household members, and place fixed
          RF receivers or ranging anchors on the floor plan.
        </div>
      </div>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-clipboard-check-outline"
        to="/admin/identity-setup"
      >
        Identity Setup
      </v-btn>
      <v-btn
        size="small"
        variant="flat"
        color="primary"
        prepend-icon="mdi-plus"
        data-test="add-device-btn"
        @click="openAddDevice"
      >
        Add device
      </v-btn>
    </div>

    <v-alert
      v-if="state.forbidden"
      type="warning"
      variant="tonal"
      class="mb-4"
      data-test="wearables-forbidden"
    >
      Viewing wearable devices and RF nodes requires the wearables permission.
    </v-alert>

    <v-alert
      v-else-if="state.error"
      type="error"
      variant="tonal"
      class="mb-4"
      data-test="wearables-error"
    >
      {{ state.error }}
      <template #append>
        <v-btn size="small" variant="text" @click="actions.loadAll">Retry</v-btn>
      </template>
    </v-alert>

    <div v-if="state.loading && !state.assignments" class="d-flex justify-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="!state.forbidden">
      <CcSegmentedToggle v-model="activeTab" :options="tabOptions" class="mb-5" />

      <!-- Devices & Bindings Tab -->
      <div v-if="activeTab === 'devices'" data-test="devices-panel">
        <v-card
          v-for="member in state.assignments?.members || []"
          :key="member.member_id"
          class="glass-card mb-4"
          :data-test="`member-wearables-${member.member_id}`"
        >
          <v-card-title class="d-flex align-center justify-space-between">
            <span class="text-subtitle-1 font-weight-bold">{{ member.member_name }}</span>
            <v-chip size="small" variant="tonal">
              {{ member.devices.length }} {{ member.devices.length === 1 ? "device" : "devices" }}
            </v-chip>
          </v-card-title>
          <v-divider />
          <v-table density="comfortable">
            <thead>
              <tr>
                <th>Label</th>
                <th>Tag ID</th>
                <th>Kind</th>
                <th>Adapter</th>
                <th>Battery</th>
                <th>Consent by</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="dev in member.devices" :key="dev.device_id">
                <td>{{ dev.label }}</td>
                <td>
                  <code>{{ dev.tag_id }}</code>
                  <div
                    v-if="dev.physical_device_id"
                    class="text-caption text-medium-emphasis"
                    :data-test="`physical-device-${dev.tag_id}`"
                  >
                    Physical device {{ dev.physical_device_id }}
                  </div>
                </td>
                <td>{{ dev.device_kind }}</td>
                <td>{{ dev.adapter_id }}</td>
                <td>
                  {{
                    dev.last_battery_fraction != null
                      ? `${Math.round(dev.last_battery_fraction * 100)}%`
                      : "Unknown"
                  }}
                </td>
                <td>{{ dev.consent_recorded_by }}</td>
                <td class="text-right">
                  <v-btn
                    size="small"
                    variant="text"
                    :data-test="`history-btn-${dev.tag_id}`"
                    @click="openBindingDialogFromMemberDevice(dev.device_id)"
                  >
                    History
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="tonal"
                    color="warning"
                    :data-test="`quick-unbind-${dev.tag_id}`"
                    @click="actions.unbindDevice(dev.device_id)"
                  >
                    Unbind
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>

        <v-card class="glass-card" data-test="unbound-devices-card">
          <v-card-title class="text-subtitle-1 font-weight-bold">Unbound devices</v-card-title>
          <v-divider />
          <div
            v-if="!(state.assignments?.unbound_devices || []).length"
            class="pa-6 text-center text-medium-emphasis"
          >
            No unbound wearable devices.
          </div>
          <v-table v-else density="comfortable">
            <thead>
              <tr>
                <th>Label</th>
                <th>Tag ID</th>
                <th>Kind</th>
                <th>Adapter</th>
                <th>Hardware key</th>
                <th>Status</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="dev in state.assignments?.unbound_devices || []" :key="dev.id">
                <td>{{ dev.label }}</td>
                <td>
                  <code>{{ dev.tag_id }}</code>
                  <div
                    v-if="dev.physical_device_id"
                    class="text-caption text-medium-emphasis"
                    :data-test="`physical-device-${dev.tag_id}`"
                  >
                    Physical device {{ dev.physical_device_id }}
                  </div>
                </td>
                <td>{{ dev.device_kind }}</td>
                <td>{{ dev.adapter_id }}</td>
                <td>
                  <code>{{ dev.hardware_key }}</code>
                </td>
                <td>
                  <v-chip size="small" :color="dev.is_active ? 'success' : undefined">
                    {{ dev.is_active ? "Active" : "Inactive" }}
                  </v-chip>
                </td>
                <td class="text-right">
                  <v-btn
                    size="small"
                    variant="tonal"
                    color="primary"
                    :disabled="!dev.is_active"
                    :data-test="`bind-open-${dev.tag_id}`"
                    @click="openBindingDialog(dev)"
                  >
                    Bind
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    :data-test="`toggle-active-${dev.tag_id}`"
                    @click="toggleDeviceActive(dev)"
                  >
                    {{ dev.is_active ? "Deactivate" : "Reactivate" }}
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>
      </div>

      <!-- Position Sensors Tab -->
      <PositionSensorsPanel
        v-else-if="activeTab === 'sensors'"
        :sensors="state.positionSensors"
        :rooms="state.rooms"
        :floor-plan-ready="state.floorPlanReady"
        :floor-width-m="state.floorWidthM"
        :floor-height-m="state.floorHeightM"
        :saving="state.saving"
        @create-sensor="handleCreateSensor"
        @update-sensor="handleUpdateSensor"
        @delete-sensor="confirmDeleteSensor"
      />

      <!-- RF Nodes Tab -->
      <RfNodeFloorPlanCanvas
        v-else
        :floor-plan-ready="state.floorPlanReady"
        :floor-plan-url="state.floorPlan?.floor_plan_url ?? null"
        :floor-width-m="state.floorWidthM"
        :floor-height-m="state.floorHeightM"
        :nodes="state.nodes"
        :rooms="state.rooms"
        :saving="state.saving"
        :survey-result="state.surveyResult"
        :checking-survey="state.checkingSurvey"
        @create-node="actions.addNode"
        @update-node="actions.patchNode"
        @delete-node="confirmDeleteNode"
        @run-survey="actions.runSurveyCheck"
        @clear-survey="actions.clearSurvey"
      />
    </template>

    <!-- Add Device Modal -->
    <AppDialog
      v-model="showAddDevice"
      size="md"
      persistent
      icon="mdi-watch-variant"
      label="Wearables"
      title="Register wearable device"
      confirm-label="Register"
      :confirm-loading="state.saving"
      :confirm-disabled="!canCreateDevice"
      @confirm="submitAddDevice"
    >
      <div class="px-6 py-5">
        <v-text-field
          v-model="newDevice.label"
          label="Label"
          placeholder="Grandma's wristband"
          class="mb-2"
          data-test="new-device-label"
        />
        <v-text-field
          v-model="newDevice.tag_id"
          label="Tag ID"
          placeholder="grandma-band-1"
          class="mb-2"
          data-test="new-device-tag-id"
        />
        <v-row dense class="mb-2">
          <v-col cols="6">
            <v-select
              v-model="newDevice.device_kind"
              label="Device kind"
              :items="deviceKindOptions"
              item-title="title"
              item-value="value"
              data-test="new-device-kind"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="newDevice.adapter_id"
              label="Adapter ID"
              placeholder="ble-home"
              data-test="new-device-adapter"
            />
          </v-col>
        </v-row>
        <v-text-field
          v-model="newDevice.hardware_key"
          label="Hardware key"
          hint="Radio identifier reported by the receiver (for iBeacon: iBeacon:<uuid>-<major>-<minor>, found in the beacon companion app or receiver MQTT logs)"
          persistent-hint
          data-test="new-device-hw-key"
        />
        <v-text-field
          v-model="newDevice.physical_device_id"
          label="Physical device ID (optional)"
          placeholder="watch-amma"
          hint="Give the BLE and UWB tags of one dual-mode watch the same value, so tracking treats them as one wearable"
          persistent-hint
          class="mt-4"
          data-test="new-device-physical-id"
        />
      </div>
    </AppDialog>

    <!-- Bind / History Modal -->
    <WearableBindingDialog
      v-model="showBindingDialog"
      :device="selectedDevice"
      :history="state.bindingHistory"
      :loading-history="state.loadingHistory"
      :saving="state.saving"
      :associations="state.deviceAssociations"
      :loading-associations="state.loadingAssociations"
      :associations-error="state.associationsError"
      :revoking-segment-id="state.revokingSegmentId"
      :resuming-tag-id="state.resumingTagId"
      @bind="handleBind"
      @unbind="actions.unbindDevice"
      @revoke-association="confirmRevokeAssociation"
      @resume-teaching="confirmResumeTeaching"
    />

    <!-- Confirm destructive / state-changing action -->
    <v-dialog v-model="confirmDialog" max-width="400" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import PositionSensorsPanel from "@/components/cts/wearables/PositionSensorsPanel.vue";
import RfNodeFloorPlanCanvas from "@/components/cts/wearables/RfNodeFloorPlanCanvas.vue";
import WearableBindingDialog from "@/components/cts/wearables/WearableBindingDialog.vue";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import { useWearables } from "@/composables/useWearables";
import type {
  PositionSensorCreate,
  PositionSensorUpdate,
  WearableBindingCreate,
  WearableDeviceOut,
} from "@/services/modules/wearables";
import { useIdentityReviewStore } from "@/stores/identityReview";

const { notify } = useNotify();
const review = useIdentityReviewStore();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();
const { state, actions } = useWearables(notify);

const activeTab = ref<"devices" | "nodes" | "sensors">("devices");
const tabOptions = [
  { value: "devices", label: "Devices & Bindings", icon: "mdi-watch-variant" },
  { value: "nodes", label: "RF Nodes & Placement", icon: "mdi-access-point-network" },
  { value: "sensors", label: "Position Sensors", icon: "mdi-radar" },
];

const deviceKindOptions = [
  { title: "BLE beacon", value: "ble_beacon" },
  { title: "Watch", value: "watch" },
  { title: "UWB tag", value: "uwb_tag" },
];

const showAddDevice = ref(false);
const newDevice = reactive({
  label: "",
  tag_id: "",
  device_kind: "ble_beacon" as "ble_beacon" | "watch" | "uwb_tag",
  adapter_id: "ble-home",
  hardware_key: "",
  physical_device_id: "",
});

const canCreateDevice = computed(
  () =>
    newDevice.label.trim().length > 0 &&
    newDevice.tag_id.trim().length > 0 &&
    newDevice.adapter_id.trim().length > 0 &&
    newDevice.hardware_key.trim().length > 0,
);

function openAddDevice() {
  newDevice.label = "";
  newDevice.tag_id = "";
  newDevice.device_kind = "ble_beacon";
  newDevice.adapter_id = "ble-home";
  newDevice.hardware_key = "";
  newDevice.physical_device_id = "";
  showAddDevice.value = true;
}

async function submitAddDevice() {
  if (!canCreateDevice.value) return;
  await actions.addDevice({
    label: newDevice.label.trim(),
    tag_id: newDevice.tag_id.trim(),
    device_kind: newDevice.device_kind,
    adapter_id: newDevice.adapter_id.trim(),
    hardware_key: newDevice.hardware_key.trim(),
    physical_device_id: newDevice.physical_device_id.trim() || null,
  });
  showAddDevice.value = false;
}

const showBindingDialog = ref(false);
const selectedDevice = ref<WearableDeviceOut | null>(null);

async function openBindingDialog(device: WearableDeviceOut) {
  selectedDevice.value = device;
  showBindingDialog.value = true;
  await Promise.all([
    actions.loadBindingHistory(device.id),
    actions.loadDeviceAssociations(device.id),
  ]);
}

async function openBindingDialogFromMemberDevice(deviceId: string) {
  const memberEntry = state.assignments?.members
    .flatMap((m) => m.devices)
    .find((d) => d.device_id === deviceId);
  if (!memberEntry) return;
  selectedDevice.value = {
    id: memberEntry.device_id,
    tag_id: memberEntry.tag_id,
    device_kind: memberEntry.device_kind,
    label: memberEntry.label,
    adapter_id: memberEntry.adapter_id,
    hardware_key: "",
    physical_device_id: memberEntry.physical_device_id ?? null,
    is_active: memberEntry.is_active,
    last_heard_at: memberEntry.last_heard_at,
    last_battery_fraction: memberEntry.last_battery_fraction,
    active_binding: null,
    created_at: memberEntry.valid_from,
    updated_at: memberEntry.valid_from,
  };
  showBindingDialog.value = true;
  await Promise.all([
    actions.loadBindingHistory(deviceId),
    actions.loadDeviceAssociations(deviceId),
  ]);
}

async function confirmRevokeAssociation(segmentId: string) {
  await review.load();
  const effect =
    review.wearableRevocationEffect() ||
    "Revoke what this wearable association taught and pause further teaching for this tag.";
  const ok = await showConfirm("Revoke what this taught?", effect);
  if (!ok) return;
  await actions.revokeAssociation(segmentId, selectedDevice.value?.id).catch(() => {});
}

async function confirmResumeTeaching(tagId: string) {
  const ok = await showConfirm(
    `Resume teaching for ${tagId}?`,
    "Confirm this wearable is back on the right wearer. Further tracking periods will teach body samples and face captures again.",
  );
  if (!ok) return;
  await actions.resumeTeaching(tagId, selectedDevice.value?.id).catch(() => {});
}

async function handleBind(deviceId: string, body: WearableBindingCreate) {
  await actions.bindDevice(deviceId, body);
}

async function toggleDeviceActive(device: WearableDeviceOut) {
  if (device.is_active) {
    const ok = await showConfirm(
      `Deactivate ${device.label}?`,
      "An inactive wearable cannot be bound and its fixes will be ignored.",
    );
    if (!ok) return;
  }
  await actions.patchDevice(device.id, { is_active: !device.is_active });
}

async function confirmDeleteNode(nodeId: string) {
  const node = state.nodes.find((n) => n.id === nodeId);
  const ok = await showConfirm(
    `Remove RF node ${node?.label || nodeId}?`,
    "This removes the node from site-config on the next sync poll.",
  );
  if (!ok) return;
  await actions.removeNode(nodeId);
}

async function handleCreateSensor(body: PositionSensorCreate) {
  await actions.addPositionSensor(body).catch(() => {});
}

async function handleUpdateSensor(sensorUuid: string, body: PositionSensorUpdate) {
  await actions.patchPositionSensor(sensorUuid, body).catch(() => {});
}

async function confirmDeleteSensor(sensorUuid: string) {
  const sensor = state.positionSensors.find((s) => s.id === sensorUuid);
  const ok = await showConfirm(
    `Remove position sensor ${sensor?.label || sensorUuid}?`,
    "Its tracks are ignored from the next site-config poll, and people it was following are no longer placed in its room.",
  );
  if (!ok) return;
  await actions.removePositionSensor(sensorUuid).catch(() => {});
}

onMounted(() => {
  actions.loadAll();
  void review.load();
});
</script>
