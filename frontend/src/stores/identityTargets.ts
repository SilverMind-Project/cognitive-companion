/**
 * The household members an operator may say a face, body, or track belongs to.
 *
 * One store for every identity decision surface, so they all offer the same people with the same
 * names. Each review page refreshes it when it opens (`load(true)`), and naming a visitor
 * refreshes it, so a member added elsewhere appears without a reload; a picker on the same page
 * reuses the cached list, and a load already in flight is shared instead of repeated.
 */

import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { ApiError } from "@/services/http";
import { getIdentityTargets, type IdentityTarget } from "@/services/modules/identity_targets";

export const useIdentityTargetsStore = defineStore("identityTargets", () => {
  const targets = ref<IdentityTarget[]>([]);
  const enrollmentAvailable = ref(true);
  const galleryAvailable = ref(true);
  const loading = ref(false);
  const loaded = ref(false);
  const error = ref("");
  const forbidden = ref(false);
  let inFlight: Promise<void> | null = null;

  const byId = computed(() => new Map(targets.value.map((t) => [t.identity_id, t])));

  async function fetchTargets(): Promise<void> {
    loading.value = true;
    error.value = "";
    forbidden.value = false;
    try {
      const envelope = await getIdentityTargets();
      targets.value = envelope.targets;
      enrollmentAvailable.value = envelope.enrollment_available;
      galleryAvailable.value = envelope.gallery_available;
      loaded.value = true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) forbidden.value = true;
      else error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
      inFlight = null;
    }
  }

  /** Load the list unless it is already loaded; `force` reloads it. Never throws. */
  function load(force = false): Promise<void> {
    if (loaded.value && !force) return Promise.resolve();
    inFlight ??= fetchTargets();
    return inFlight;
  }

  /** The member's display name, or the id itself when it is not (or no longer) a member. */
  function nameOf(identityId: string | null | undefined): string {
    if (!identityId) return "";
    return byId.value.get(identityId)?.display_name ?? identityId;
  }

  return {
    targets,
    enrollmentAvailable,
    galleryAvailable,
    loading,
    loaded,
    error,
    forbidden,
    byId,
    load,
    nameOf,
  };
});
