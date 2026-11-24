/**
 * The activity types a routine can record or wait for, from the backend's
 * `ActivityTypeEnum` (`GET /routines/activity-type-options`), never hand-typed:
 * a type the ledger does not know can never match a recorded activity.
 *
 * Fetched once per page load and shared by every editor that needs it.
 */

import { computed, reactive } from "vue";
import { api } from "@/services/api.js";

const state = reactive({ types: [] });
let pending = null;

function load() {
  if (pending === null) {
    pending = api
      .getActivityTypeOptions()
      .then((res) => {
        state.types = res.activity_types ?? [];
      })
      .catch(() => {
        // Let the next editor that mounts retry.
        pending = null;
      });
  }
  return pending;
}

/** Test seam: forget the shared list so each test starts clean. */
export function resetActivityTypeOptions() {
  state.types = [];
  pending = null;
}

export function useActivityTypeOptions() {
  void load();
  /** `{ title, value }` select items, with readable titles. */
  const items = computed(() =>
    state.types.map((value) => ({ title: value.replaceAll("_", " "), value })),
  );
  return { state, actions: { load }, items };
}
