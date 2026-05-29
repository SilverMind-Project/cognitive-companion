/**
 * U4: Single source of truth for "where is everyone now."
 *
 * Polls GET /api/v1/persons/locations (U2 PersonLocationEnvelope batch endpoint).
 * All panels that need current person locations consume this composable (D1).
 * Never construct location data client-side (D5).
 */

import { ref, onMounted, onBeforeUnmount } from "vue";
import { api } from "@/services/api.js";

/**
 * @param {{ pollMs?: number }} [opts]
 * @returns {{
 *   locations: import("vue").Ref<Array<import("../services/api.js").PersonLocationEnvelope>>,
 *   loading: import("vue").Ref<boolean>,
 *   error: import("vue").Ref<string|null>,
 *   refresh: () => Promise<void>,
 * }}
 */
export function usePersonPresence({ pollMs = 15000 } = {}) {
  const locations = ref([]);
  const loading = ref(false);
  const error = ref(null);
  let timer = null;

  async function refresh() {
    loading.value = true;
    try {
      const data = await api.getPersonLocations();
      // Deduplicate by person_id: last entry wins (should not occur with a correct SSOT).
      const seen = new Map();
      for (const loc of data || []) {
        seen.set(loc.person_id, loc);
      }
      locations.value = [...seen.values()];
      error.value = null;
    } catch (e) {
      error.value = e?.message || "Failed to load person locations";
    } finally {
      loading.value = false;
    }
  }

  onMounted(() => {
    refresh();
    timer = setInterval(refresh, pollMs);
  });

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
  });

  return { locations, loading, error, refresh };
}
