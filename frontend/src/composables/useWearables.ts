/**
 * Composable owning state and actions for wearable devices, bindings, RF nodes, and position sensors.
 */

import { reactive } from "vue";
import { getRooms, type RoomOut } from "@/services/modules/rooms";
import {
  bindWearableDevice,
  checkRfNodeSurvey,
  createPositionSensor,
  createRfNode,
  createWearableDevice,
  deletePositionSensor,
  deleteRfNode,
  getHouseholdFloorPlan,
  getWearableAssignments,
  listDeviceAssociations,
  listDeviceBindings,
  listPositionSensors,
  listRfNodes,
  resumeWearableTagTeaching,
  revokeWearableAssociation,
  unbindWearableDevice,
  updatePositionSensor,
  updateRfNode,
  updateWearableDevice,
  type FloorPlanOut,
  type PositionSensorCreate,
  type PositionSensorOut,
  type PositionSensorUpdate,
  type RfNodeCreate,
  type RfNodeOut,
  type RfNodeSurveyCheckOut,
  type RfNodeSurveyCheckRequest,
  type RfNodeUpdate,
  type WearableAssignmentsOut,
  type WearableBindingCreate,
  type WearableBindingOut,
  type WearableDeviceAssociationsOut,
  type WearableDeviceCreate,
  type WearableDeviceUpdate,
} from "@/services/modules/wearables";

type NotifyFn = (message: string, color?: string) => void;

function isForbidden(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    (err as { status?: number }).status === 403
  );
}

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

export function useWearables(notify?: NotifyFn) {
  const state = reactive({
    loading: false,
    saving: false,
    forbidden: false,
    error: null as string | null,
    assignments: null as WearableAssignmentsOut | null,
    nodes: [] as RfNodeOut[],
    positionSensors: [] as PositionSensorOut[],
    floorPlanReady: false,
    floorPlanId: null as string | null,
    floorWidthM: null as number | null,
    floorHeightM: null as number | null,
    floorPlan: null as FloorPlanOut | null,
    rooms: [] as RoomOut[],
    bindingHistory: [] as WearableBindingOut[],
    loadingHistory: false,
    deviceAssociations: null as WearableDeviceAssociationsOut | null,
    loadingAssociations: false,
    associationsError: null as string | null,
    revokingSegmentId: null as string | null,
    resumingTagId: null as string | null,
    surveyResult: null as RfNodeSurveyCheckOut | null,
    checkingSurvey: false,
  });

  async function loadAll() {
    state.loading = true;
    state.error = null;
    state.forbidden = false;
    try {
      const [assignments, nodesResp, sensorsResp, floorPlan, rooms] = await Promise.all([
        getWearableAssignments(),
        listRfNodes(),
        listPositionSensors(),
        getHouseholdFloorPlan().catch(() => null),
        getRooms().catch(() => []),
      ]);
      state.assignments = assignments;
      state.nodes = nodesResp.items;
      state.positionSensors = sensorsResp.items;
      state.floorPlanReady = nodesResp.floor_plan_ready;
      state.floorPlanId = nodesResp.floor_plan_id;
      state.floorWidthM = nodesResp.floor_width_m;
      state.floorHeightM = nodesResp.floor_height_m;
      state.floorPlan = floorPlan;
      state.rooms = rooms;
    } catch (err) {
      if (isForbidden(err)) {
        state.forbidden = true;
      } else {
        state.error = errorMessage(err);
      }
    } finally {
      state.loading = false;
    }
  }

  async function addDevice(body: WearableDeviceCreate) {
    state.saving = true;
    try {
      const created = await createWearableDevice(body);
      notify?.(`Registered wearable ${created.label}`);
      await loadAll();
      return created;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function patchDevice(deviceId: string, body: WearableDeviceUpdate) {
    state.saving = true;
    try {
      const updated = await updateWearableDevice(deviceId, body);
      notify?.(`Updated wearable ${updated.label}`);
      await loadAll();
      return updated;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function loadBindingHistory(deviceId: string) {
    state.loadingHistory = true;
    try {
      state.bindingHistory = await listDeviceBindings(deviceId);
    } catch (err) {
      notify?.(errorMessage(err), "error");
      state.bindingHistory = [];
    } finally {
      state.loadingHistory = false;
    }
  }

  async function loadDeviceAssociations(deviceId: string) {
    state.loadingAssociations = true;
    state.associationsError = null;
    try {
      state.deviceAssociations = await listDeviceAssociations(deviceId);
    } catch (err) {
      state.deviceAssociations = null;
      state.associationsError = errorMessage(err);
    } finally {
      state.loadingAssociations = false;
    }
  }

  async function revokeAssociation(segmentId: string, deviceId?: string) {
    state.revokingSegmentId = segmentId;
    try {
      const result = await revokeWearableAssociation(segmentId);
      const promoted = result.already_promoted_faces ?? [];
      const promotedNote = promoted.length
        ? ` ${promoted.length} already-promoted face prototype(s) kept for manual review.`
        : "";
      notify?.(
        `Revoked wearable teaching (${result.gallery_rows_demoted} body sample(s) demoted).${promotedNote}`,
      );
      if (deviceId) {
        await loadDeviceAssociations(deviceId);
      }
      return result;
    } catch (err) {
      notify?.(
        isForbidden(err)
          ? "Revoking wearable teaching requires the caregiver-admin permission."
          : errorMessage(err),
        "error",
      );
      throw err;
    } finally {
      state.revokingSegmentId = null;
    }
  }

  async function resumeTeaching(tagId: string, deviceId?: string) {
    state.resumingTagId = tagId;
    try {
      const result = await resumeWearableTagTeaching(tagId);
      notify?.(result.resumed ? `Resumed teaching for ${tagId}` : `No open hold on ${tagId}`);
      if (deviceId) {
        await loadDeviceAssociations(deviceId);
      }
      return result;
    } catch (err) {
      notify?.(
        isForbidden(err)
          ? "Resuming wearable teaching requires the caregiver-admin permission."
          : errorMessage(err),
        "error",
      );
      throw err;
    } finally {
      state.resumingTagId = null;
    }
  }

  async function bindDevice(deviceId: string, body: WearableBindingCreate) {
    state.saving = true;
    try {
      const bound = await bindWearableDevice(deviceId, body);
      notify?.("Wearable bound with recorded consent");
      await Promise.all([loadAll(), loadBindingHistory(deviceId)]);
      return bound;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function unbindDevice(deviceId: string) {
    state.saving = true;
    try {
      const closed = await unbindWearableDevice(deviceId);
      notify?.("Wearable unbound");
      await Promise.all([loadAll(), loadBindingHistory(deviceId)]);
      return closed;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function addNode(body: RfNodeCreate) {
    state.saving = true;
    try {
      const created = await createRfNode(body);
      notify?.(`Placed RF node ${created.label}`);
      await loadAll();
      return created;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function patchNode(nodeId: string, body: RfNodeUpdate) {
    state.saving = true;
    try {
      const updated = await updateRfNode(nodeId, body);
      notify?.(`Updated RF node ${updated.label}`);
      await loadAll();
      return updated;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function removeNode(nodeId: string) {
    state.saving = true;
    try {
      await deleteRfNode(nodeId);
      notify?.("Removed RF node");
      await loadAll();
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function addPositionSensor(body: PositionSensorCreate) {
    state.saving = true;
    try {
      const created = await createPositionSensor(body);
      notify?.(`Registered position sensor ${created.label}`);
      await loadAll();
      return created;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function patchPositionSensor(sensorUuid: string, body: PositionSensorUpdate) {
    state.saving = true;
    try {
      const updated = await updatePositionSensor(sensorUuid, body);
      notify?.(`Updated position sensor ${updated.label}`);
      await loadAll();
      return updated;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function removePositionSensor(sensorUuid: string) {
    state.saving = true;
    try {
      await deletePositionSensor(sensorUuid);
      notify?.("Removed position sensor");
      await loadAll();
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.saving = false;
    }
  }

  async function runSurveyCheck(body: RfNodeSurveyCheckRequest) {
    state.checkingSurvey = true;
    try {
      state.surveyResult = await checkRfNodeSurvey(body);
      return state.surveyResult;
    } catch (err) {
      notify?.(errorMessage(err), "error");
      throw err;
    } finally {
      state.checkingSurvey = false;
    }
  }

  function clearSurvey() {
    state.surveyResult = null;
  }

  return {
    state,
    actions: {
      loadAll,
      addDevice,
      patchDevice,
      loadBindingHistory,
      loadDeviceAssociations,
      revokeAssociation,
      resumeTeaching,
      bindDevice,
      unbindDevice,
      addNode,
      patchNode,
      removeNode,
      addPositionSensor,
      patchPositionSensor,
      removePositionSensor,
      runSurveyCheck,
      clearSurvey,
    },
  };
}
