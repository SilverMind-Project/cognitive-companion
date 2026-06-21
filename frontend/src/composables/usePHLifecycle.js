/**
 * PH lifecycle operations: merge and split.
 *
 * These are PH-structure operations, distinct from identity-label correction
 * (which lives in the shared `useIdentityCorrection` workflow). They are kept
 * separate because merging/splitting changes the hypothesis graph, not just an
 * effective label. Returns `{ state, actions }` per engineering-standards
 * Section 17.
 */

import { ref } from "vue";
import { ctsPh } from "@/services/cts_ph";

export function usePHLifecycle(notify) {
  const saving = ref(false);
  const lastRevision = ref(null);

  async function apply(action, payload) {
    saving.value = true;
    lastRevision.value = null;
    try {
      let result;
      if (action === "merge") {
        result = await ctsPh.merge({
          source_ph_id: payload.source_ph_id,
          target_ph_id: payload.target_ph_id,
          reason: payload.reason,
        });
      } else if (action === "split") {
        result = await ctsPh.split(payload.ph_id, {
          at_observation_id: payload.at_observation_id,
          reason: payload.reason,
        });
      } else {
        throw new Error(`Unknown lifecycle action: ${action}`);
      }
      lastRevision.value = result?.revision || null;
      if (notify) notify.success(action === "merge" ? "PHs merged" : "PH split");
      return result;
    } catch (err) {
      if (notify) notify.error(String(err.message || err));
      throw err;
    } finally {
      saving.value = false;
    }
  }

  return {
    state: { saving, lastRevision },
    actions: { apply },
  };
}
