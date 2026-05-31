/**
 * N3: PH detail composable -- parallel fetch of detail, observations, keyframes, trail.
 *
 * Returns { state, actions } per engineering-standards Section 17.
 */

import { ref } from "vue";
import { ctsPh } from "@/services/cts_ph";

export function usePHDetail() {
  const detail = ref(null);
  const observations = ref([]);
  const keyframes = ref([]);
  const trail = ref([]);
  const coPresent = ref([]);
  const loading = ref(false);
  const errors = ref([]);
  const panelErrors = ref({
    detail: "",
    observations: "",
    keyframes: "",
    trail: "",
    coPresent: "",
  });

  async function fetch(phId) {
    loading.value = true;
    errors.value = [];
    panelErrors.value = {
      detail: "",
      observations: "",
      keyframes: "",
      trail: "",
      coPresent: "",
    };
    detail.value = null;
    observations.value = [];
    keyframes.value = [];
    trail.value = [];
    coPresent.value = [];

    const results = await Promise.allSettled([
      ctsPh.get(phId),
      ctsPh.observations(phId, 200),
      ctsPh.keyframes(phId, 24),
      ctsPh.trail(phId),
      ctsPh.coPresent(phId),
    ]);

    const [detailR, obsR, kfR, trailR, coR] = results;
    if (detailR.status === "fulfilled") detail.value = detailR.value;
    else {
      panelErrors.value.detail = detailR.reason?.message || "failed";
      errors.value.push("detail: " + panelErrors.value.detail);
    }

    if (obsR.status === "fulfilled") observations.value = obsR.value.items || [];
    else {
      panelErrors.value.observations = obsR.reason?.message || "failed";
      errors.value.push("observations: " + panelErrors.value.observations);
    }

    if (kfR.status === "fulfilled") keyframes.value = kfR.value.items || [];
    else {
      panelErrors.value.keyframes = kfR.reason?.message || "failed";
      errors.value.push("keyframes: " + panelErrors.value.keyframes);
    }

    if (trailR.status === "fulfilled") trail.value = trailR.value.points || [];
    else {
      panelErrors.value.trail = trailR.reason?.message || "failed";
      errors.value.push("trail: " + panelErrors.value.trail);
    }

    if (coR.status === "fulfilled") coPresent.value = coR.value.co_present || [];
    else {
      panelErrors.value.coPresent = coR.reason?.message || "failed";
      errors.value.push("co-present: " + panelErrors.value.coPresent);
    }

    loading.value = false;
  }

  return {
    state: { detail, observations, keyframes, trail, coPresent, loading, errors, panelErrors },
    actions: { fetch },
  };
}
