/**
 * Composable owning state and actions for wearable devices, bindings, and RF nodes.
 */

import { reactive } from "vue";
import { getRooms, type RoomOut } from "@/services/modules/rooms";
import {
  bindWearableDevice,
  checkRfNodeSurvey,
  createRfNode,
  createWearableDevice,
  deleteRfNode,
  getHouseholdFloorPlan,
  getWearableAssignments,
  listDeviceBindings,
  listRfNodes,
  unbindWearableDevice,
  updateRfNode,
  updateWearableDevice,
  type FloorPlanOut,
  type RfNodeCreate,
  type RfNodeOut,
  type RfNodeSurveyCheckOut,
  type RfNodeSurveyCheckRequest,
  type RfNodeUpdate,
  type WearableAssignmentsOut,
  type WearableBindingCreate,
  type WearableBindingOut,
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
    floorPlanReady: false,
    floorPlanId: null as string | null,
    floorWidthM: null as number | null,
    floorHeightM: null as number | null,
    floorPlan: null as FloorPlanOut | null,
    rooms: [] as RoomOut[],
    bindingHistory: [] as WearableBindingOut[],
    loadingHistory: false,
    surveyResult: null as RfNodeSurveyCheckOut | null,
    checkingSurvey: false,
  });

  async function loadAll() {
    state.loading = true;
    state.error = null;
    state.forbidden = false;
    try {
      const [assignments, nodesResp, floorPlan, rooms] = await Promise.all([
        getWearableAssignments(),
        listRfNodes(),
        getHouseholdFloorPlan().catch(() => null),
        getRooms().catch(() => []),
      ]);
      state.assignments = assignments;
      state.nodes = nodesResp.items;
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
      bindDevice,
      unbindDevice,
      addNode,
      patchNode,
      removeNode,
      runSurveyCheck,
      clearSurvey,
    },
  };
}
