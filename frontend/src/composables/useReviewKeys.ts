/**
 * The shared keyboard for one-at-a-time identity review.
 *
 * Every review surface uses the same keys: 1 to 9 choose a member, `n` someone not in the
 * household, `x` not usable, and the arrows move through the queue. Keys are ignored while typing
 * in a field, with a modifier held, or while `enabled` says no (a dialog is open, nothing is
 * selected). The surface decides what each key does; this only maps keys to intents.
 */

import { onBeforeUnmount, onMounted } from "vue";

import { MAX_KEYED_MEMBERS, VERDICT_KEYS, type ReviewVerdict } from "@/constants/identityReview";

export interface ReviewKeyHandlers {
  enabled: () => boolean;
  /** Verdicts the surface accepts right now (from the server's vocabulary). */
  verdicts: () => readonly ReviewVerdict[];
  onMember: (position: number) => void;
  onVerdict: (verdict: ReviewVerdict) => void;
  onNext?: () => void;
  onPrevious?: () => void;
}

const _TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** Which intent a key stands for, or null; exported for direct tests. */
export function reviewKeyIntent(
  key: string,
  verdicts: readonly ReviewVerdict[],
):
  | { kind: "member"; position: number }
  | { kind: "verdict"; verdict: ReviewVerdict }
  | { kind: "next" }
  | { kind: "previous" }
  | null {
  if (/^[1-9]$/.test(key) && Number(key) <= MAX_KEYED_MEMBERS) {
    return verdicts.includes("is_member") ? { kind: "member", position: Number(key) - 1 } : null;
  }
  const verdict = verdicts.find((v) => VERDICT_KEYS[v] === key);
  if (verdict) return { kind: "verdict", verdict };
  if (key === "ArrowRight") return { kind: "next" };
  if (key === "ArrowLeft") return { kind: "previous" };
  return null;
}

export function useReviewKeys(handlers: ReviewKeyHandlers) {
  function onKeydown(event: KeyboardEvent) {
    if (!handlers.enabled() || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target as HTMLElement | null;
    if (target && (_TYPING.has(target.tagName) || target.isContentEditable)) return;
    const intent = reviewKeyIntent(event.key, handlers.verdicts());
    if (intent === null) return;
    if (intent.kind === "member") handlers.onMember(intent.position);
    else if (intent.kind === "verdict") handlers.onVerdict(intent.verdict);
    else if (intent.kind === "next") {
      if (!handlers.onNext) return;
      handlers.onNext();
    } else {
      if (!handlers.onPrevious) return;
      handlers.onPrevious();
    }
    event.preventDefault();
  }

  onMounted(() => window.addEventListener("keydown", onKeydown));
  onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

  return { state: {}, actions: { onKeydown } };
}
