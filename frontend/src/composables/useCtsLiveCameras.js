import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { cts } from "@/services/cts";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket.js";
import { useLiveIdentityCache } from "@/composables/useLiveIdentityCache.js";
import { useNotify } from "@/composables/useNotify.js";

const STALE_THRESHOLD_S = 15;
const SNAPSHOT_POLL_MS = 5_000;
const SELECTED_STORAGE_KEY = "cts_live_selected_cameras";

function loadSelectedFromStorage() {
  try {
    return JSON.parse(localStorage.getItem(SELECTED_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

/**
 * Camera/socket state for the CTS live view: the per-camera frame+detection state fed by the
 * WS, the known-camera list, per-slot selection (persisted to localStorage), snapshot polling,
 * and staleness. `layout` is a ref to the current grid layout (1/4/9/16), read by
 * cameraIdForSlot for the per-layout slot-selection map.
 */
export function useCtsLiveCameras(layout) {
  const { notify } = useNotify();
  const { mergeIdentityCache, smoothKeypoints } = useLiveIdentityCache();

  const cameras = ref({});
  // camera_id → blob URL for go2rtc snapshot (fallback when WS is idle)
  const snapshotUrls = ref({});
  // Full camera objects loaded from the API on mount
  const cameraList = ref([]);
  // Camera IDs loaded from the API (ensures slots populate before first WS event)
  const knownCameraIds = ref([]);
  const now = ref(Date.now());
  let _freshnessTimer = null;
  let _snapshotTimer = null;

  const selectedCameras = ref(loadSelectedFromStorage());

  function persistSelected() {
    localStorage.setItem(SELECTED_STORAGE_KEY, JSON.stringify(selectedCameras.value));
  }

  watch(selectedCameras, persistSelected, { deep: true });

  async function loadKnownCameras() {
    try {
      const data = await cts.getCameras();
      const list = Array.isArray(data) ? data : data.cameras || [];
      cameraList.value = list;
      knownCameraIds.value = list.map((c) => c.id);
      console.debug("[cts_live] cameras loaded", {
        count: knownCameraIds.value.length,
        ids: knownCameraIds.value,
      });
    } catch (err) {
      console.warn("[cts_live] camera list fetch failed", err);
    }
  }

  async function pollSnapshots() {
    const ids = [...new Set([...knownCameraIds.value, ...Object.keys(cameras.value)])];
    console.debug("[cts_live] polling snapshots", { camera_count: ids.length, ids });
    await Promise.allSettled(
      ids.map(async (id) => {
        try {
          const url = await cts.getSnapshot(id);
          if (snapshotUrls.value[id]) URL.revokeObjectURL(snapshotUrls.value[id]);
          snapshotUrls.value = { ...snapshotUrls.value, [id]: url };
          console.debug("[cts_live] snapshot fetched", { camera_id: id });
        } catch (err) {
          console.warn("[cts_live] snapshot fetch failed", { camera_id: id, error: String(err) });
        }
      }),
    );
  }

  onMounted(async () => {
    _freshnessTimer = setInterval(() => {
      now.value = Date.now();
    }, 5000);
    await loadKnownCameras();
    pollSnapshots();
    _snapshotTimer = setInterval(pollSnapshots, SNAPSHOT_POLL_MS);
  });
  onUnmounted(() => {
    clearInterval(_freshnessTimer);
    clearInterval(_snapshotTimer);
    for (const url of Object.values(snapshotUrls.value)) URL.revokeObjectURL(url);
  });

  function onMessage(msg) {
    if (msg.type === "cts_live_frame") {
      if (!msg.camera_id) {
        console.warn("[cts_live] WS frame missing camera_id", msg);
        return;
      }
      console.debug("[cts_live] WS frame received", {
        camera_id: msg.camera_id,
        has_frame_url: !!msg.frame_url,
        has_minio_key: !!msg.minio_key,
        detection_count: msg.detections?.length ?? 0,
      });
      // Apply temporal smoothing to pose keypoints before rendering.
      msg.detections = smoothKeypoints(msg.detections);
      // Fill in last-known identity for detections that lack one this frame.
      msg.detections = mergeIdentityCache(msg.detections, msg.camera_id);
      cameras.value = {
        ...cameras.value,
        [msg.camera_id]: {
          camera_id: msg.camera_id,
          detections: msg.detections || [],
          event_time: msg.event_time,
          room_name: msg.room_name,
          minio_key: msg.minio_key || null,
          frame_url: msg.frame_url || null,
          frame_width: msg.frame_width || 1920,
          frame_height: msg.frame_height || 1080,
          lastSeenMs: Date.now(),
        },
      };
    } else if (msg.type === "cts_identity_revision") {
      const prev = msg.previous_identity_id || "unknown";
      const next = msg.new_identity_id || "unknown";
      notify.info(`Identity corrected: ${prev} → ${next}`);
    } else {
      console.debug("[cts_live] WS unknown message type", msg.type, Object.keys(msg));
    }
  }

  const { status: wsStatus } = useCtsWebSocket(onMessage);

  // Merged, sorted list of camera IDs (WS + static camera list from API)
  const allCameraIds = computed(() => {
    const merged = new Set([...knownCameraIds.value, ...Object.keys(cameras.value)]);
    return [...merged].sort();
  });

  const availableCameras = computed(() =>
    cameraList.value.map((c) => ({ id: c.id, name: c.name || c.id })),
  );

  function cameraIdForSlot(slot) {
    const forLayout = selectedCameras.value[layout.value] || {};
    const selectedId = forLayout[slot];
    if (selectedId && availableCameras.value.some((c) => c.id === selectedId)) {
      return selectedId;
    }
    return allCameraIds.value[slot] ?? null;
  }

  function onSlotCameraChange(slot, cameraId) {
    const current = { ...(selectedCameras.value[layout.value] || {}) };
    if (cameraId) {
      current[slot] = cameraId;
    } else {
      delete current[slot];
    }
    selectedCameras.value = {
      ...selectedCameras.value,
      [layout.value]: current,
    };
  }

  function cameraForSlot(slot) {
    const id = cameraIdForSlot(slot);
    return id ? (cameras.value[id] ?? null) : null;
  }

  function onFrameError(_event, cam) {
    const cameraId = cam?.camera_id;
    if (!cameraId || !cameras.value[cameraId]) return;
    console.warn("[cts_live] frame_url load failed", {
      camera_id: cameraId,
      prev_frame_url: cameras.value[cameraId].frame_url?.substring(0, 80),
    });
    cameras.value = {
      ...cameras.value,
      [cameraId]: { ...cameras.value[cameraId], frame_url: null },
    };
  }

  function cameraAgeS(cam) {
    if (!cam?.lastSeenMs) return null;
    return (now.value - cam.lastSeenMs) / 1000;
  }

  function isCameraStale(cam) {
    const age = cameraAgeS(cam);
    return age !== null && age > STALE_THRESHOLD_S;
  }

  function staleLabel(cam) {
    const age = cameraAgeS(cam);
    if (age === null) return "";
    if (age < 60) return `${Math.round(age)}s ago`;
    return `${Math.round(age / 60)}m ago`;
  }

  return {
    cameras,
    snapshotUrls,
    wsStatus,
    allCameraIds,
    availableCameras,
    cameraIdForSlot,
    onSlotCameraChange,
    cameraForSlot,
    onFrameError,
    isCameraStale,
    staleLabel,
  };
}
