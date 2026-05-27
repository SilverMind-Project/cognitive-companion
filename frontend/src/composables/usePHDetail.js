/**
 * N3: PH detail composable — parallel fetch of detail, observations, keyframes, trail.
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

  async function fetch(phId) {
    loading.value = true;
    errors.value = [];
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
    else errors.value.push("detail: " + (detailR.reason?.message || "failed"));

    if (obsR.status === "fulfilled") observations.value = obsR.value.items || [];
    else errors.value.push("observations: " + (obsR.reason?.message || "failed"));

    if (kfR.status === "fulfilled") keyframes.value = kfR.value.items || [];
    // keyframes failure is non-critical

    if (trailR.status === "fulfilled") trail.value = trailR.value.points || [];
    // trail failure is non-critical

    if (coR.status === "fulfilled") coPresent.value = coR.value.co_present || [];

    loading.value = false;
  }

  return { detail, observations, keyframes, trail, coPresent, loading, errors, fetch };
}
