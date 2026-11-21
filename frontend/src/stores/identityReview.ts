/**
 * What each identity review decision changes, in the server's words.
 *
 * The server owns these sentences (one module, `services/identity_review/vocabulary.py`); every
 * review surface previews a decision with them before it is confirmed, and the batch response
 * repeats the same sentence after it applies. The text never changes while the app runs, so it
 * loads once and is shared; a load in flight is shared too.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import {
  getReviewVocabulary,
  type ReviewSurface,
  type ReviewVerdict,
  type ReviewVocabulary,
} from "@/services/modules/identity_targets";

type SurfaceVocabulary = ReviewVocabulary["surfaces"][number];
type VerdictVocabulary = SurfaceVocabulary["verdicts"][number];

export const useIdentityReviewStore = defineStore("identityReview", () => {
  const vocabulary = ref<ReviewVocabulary | null>(null);
  const error = ref("");
  let inFlight: Promise<void> | null = null;

  async function fetchVocabulary(): Promise<void> {
    error.value = "";
    try {
      vocabulary.value = await getReviewVocabulary();
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      inFlight = null;
    }
  }

  /** Load once; never throws (a failure is in `error` and the effect lines stay empty). */
  function load(): Promise<void> {
    if (vocabulary.value) return Promise.resolve();
    inFlight ??= fetchVocabulary();
    return inFlight;
  }

  function surface(name: ReviewSurface): SurfaceVocabulary | null {
    return vocabulary.value?.surfaces.find((s) => s.surface === name) ?? null;
  }

  function verdict(name: ReviewSurface, value: ReviewVerdict): VerdictVocabulary | null {
    return surface(name)?.verdicts.find((v) => v.verdict === value) ?? null;
  }

  /** The effect sentence, with the member's name filled in; empty until the text has loaded. */
  function effect(name: ReviewSurface, value: ReviewVerdict, member?: string | null): string {
    const text = verdict(name, value)?.effect ?? "";
    const placeholder = vocabulary.value?.member_placeholder;
    if (!placeholder) return text;
    return text.split(placeholder).join(member || "the chosen member");
  }

  /** Which decisions on the surface can change enrollment, in one sentence. */
  function guarantee(name: ReviewSurface): string {
    return surface(name)?.guarantee ?? "";
  }

  /** What revoking one wearable association's teaching changes, in the server's words. */
  function wearableRevocationEffect(): string {
    return vocabulary.value?.wearable_revocation_effect ?? "";
  }

  return {
    vocabulary,
    error,
    load,
    surface,
    verdict,
    effect,
    guarantee,
    wearableRevocationEffect,
  };
});
