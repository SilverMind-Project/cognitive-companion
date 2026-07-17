import { ref, computed } from "vue";
import { cts } from "@/services/cts.js";

/** Camera list, selection, and snapshot loading for the calibration view. */
export function useCalibrationCamera(notify) {
  const cameras = ref([]);
  const selectedCameraId = ref(null);
  const selectedCamera = computed(
    () => cameras.value.find((c) => c.id === selectedCameraId.value) ?? null,
  );
  const snapshotUrl = ref(null);
  const snapshotLoading = ref(false);
  const existingCalibration = ref(false);

  async function loadCameras() {
    try {
      cameras.value = await cts.getCameras();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function loadSnapshot() {
    if (!selectedCameraId.value) return;
    snapshotLoading.value = true;
    if (snapshotUrl.value) {
      URL.revokeObjectURL(snapshotUrl.value);
      snapshotUrl.value = null;
    }
    try {
      snapshotUrl.value = await cts.getSnapshot(selectedCameraId.value);
    } catch (e) {
      notify(`Snapshot failed: ${e.message}`, "warning");
    } finally {
      snapshotLoading.value = false;
    }
  }

  async function loadExistingCalibration() {
    if (!selectedCameraId.value) return;
    try {
      await cts.getHomography(selectedCameraId.value);
      existingCalibration.value = true;
    } catch {
      existingCalibration.value = false;
    }
  }

  return {
    cameras,
    selectedCameraId,
    selectedCamera,
    snapshotUrl,
    snapshotLoading,
    existingCalibration,
    loadCameras,
    loadSnapshot,
    loadExistingCalibration,
  };
}
