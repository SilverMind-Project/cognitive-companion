/**
 * N3: PH correction composable — apply correct/merge/split with toasts.
 */

import { ref } from "vue";
import { ctsPh } from "@/services/cts_ph";

export function usePHCorrection(notify) {
  const saving = ref(false);
  const lastRevision = ref(null);

  async function apply(action, payload) {
    saving.value = true;
    lastRevision.value = null;
    try {
      let result;
      if (action === "correct") {
        result = await ctsPh.correct(payload.ph_id, {
          new_identity_id: payload.new_identity_id,
          reason: payload.reason,
        });
      } else if (action === "merge") {
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
      }
      lastRevision.value = result?.revision || null;
      if (notify) notify.success("Correction applied");
      return result;
    } catch (err) {
      const msg = String(err.message || err);
      if (notify) notify.error(msg);
      throw err;
    } finally {
      saving.value = false;
    }
  }

  return { saving, lastRevision, apply };
}
