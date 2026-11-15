<template>
  <div data-test="verdict-bar">
    <v-alert
      v-if="review.error && !surfaceVocabulary"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-2"
      data-test="vocabulary-error"
    >
      Could not load the review decisions: {{ review.error }}
      <template #append>
        <v-btn size="small" variant="text" @click="review.load()">Retry</v-btn>
      </template>
    </v-alert>
    <div class="d-flex flex-wrap ga-2">
      <template v-if="memberVerdict">
        <v-btn
          v-for="(member, position) in keyedMembers"
          :key="member.identity_id"
          size="small"
          :variant="member.identity_id === proposedId ? 'flat' : 'tonal'"
          :color="member.identity_id === proposedId ? 'primary' : undefined"
          :disabled="disabled || membersDisabled || memberUnusable(member)"
          :title="memberTitle(member)"
          :data-test="`member-${member.identity_id}`"
          @click="$emit('member', member.identity_id)"
        >
          <kbd class="mr-2">{{ position + 1 }}</kbd
          >{{ member.display_name }}
        </v-btn>
      </template>
      <v-btn
        v-for="verdict in otherVerdicts"
        :key="verdict.verdict"
        size="small"
        variant="tonal"
        :disabled="disabled"
        :title="verdict.effect"
        :data-test="`verdict-${verdict.verdict}`"
        @click="$emit('verdict', verdict.verdict)"
      >
        <kbd v-if="VERDICT_KEYS[verdict.verdict]" class="mr-2">{{
          VERDICT_KEYS[verdict.verdict]
        }}</kbd
        >{{ VERDICT_LABELS[verdict.verdict] }}
      </v-btn>
      <slot />
    </div>
    <div
      v-if="membersDisabled && membersDisabledReason"
      class="text-caption mt-2"
      data-test="members-disabled-reason"
    >
      {{ membersDisabledReason }}
    </div>
    <div class="text-caption text-medium-emphasis mt-2" data-test="verdict-keys">
      Keys: {{ keysHint }}.
      <span v-if="guarantee" data-test="verdict-guarantee">{{ guarantee }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * The decision buttons for one identity subject, the same on every review surface.
 *
 * Members come first, numbered for the keyboard (the system's proposal, if any, is highlighted),
 * then the other verdicts the server lists for this surface, each with its key and its effect as
 * a tooltip; the surface's guarantee (what can and cannot change enrollment) sits underneath. The
 * bar only emits intents: the surface maps a member or verdict to its owner's action and decides
 * whether it needs a confirm first. Surface-specific actions (skip, delete, undo) go in the slot.
 */
import { computed, onMounted } from "vue";

import {
  MAX_KEYED_MEMBERS,
  VERDICT_KEYS,
  VERDICT_LABELS,
  type ReviewVerdict,
} from "@/constants/identityReview";
import type { IdentityTarget, ReviewSurface } from "@/services/modules/identity_targets";
import { useIdentityReviewStore } from "@/stores/identityReview";

const props = withDefaults(
  defineProps<{
    surface: ReviewSurface;
    members: IdentityTarget[];
    proposedId?: string | null;
    disabled?: boolean;
    /** Members cannot be chosen right now (for example the server says the subject is ineligible). */
    membersDisabled?: boolean;
    membersDisabledReason?: string;
    /** The surface moves through a queue with the arrow keys. */
    navigable?: boolean;
  }>(),
  {
    proposedId: null,
    disabled: false,
    membersDisabled: false,
    membersDisabledReason: "",
    navigable: true,
  },
);
defineEmits<{ member: [identityId: string]; verdict: [verdict: ReviewVerdict] }>();

const review = useIdentityReviewStore();

const surfaceVocabulary = computed(() => review.surface(props.surface));
const memberVerdict = computed(() => review.verdict(props.surface, "is_member"));
// "Someone new" is never a one-key decision: it creates a person and needs a name.
const otherVerdicts = computed(
  () =>
    surfaceVocabulary.value?.verdicts.filter(
      (v) => v.verdict !== "is_member" && v.verdict !== "new_person",
    ) ?? [],
);
const keyedMembers = computed(() => props.members.slice(0, MAX_KEYED_MEMBERS));
const guarantee = computed(() => review.guarantee(props.surface));

function memberUnusable(member: IdentityTarget): boolean {
  return Boolean(memberVerdict.value?.needs_enrolled_face) && member.face_enrolled === false;
}

function memberTitle(member: IdentityTarget): string {
  if (memberUnusable(member)) return `${member.display_name} has no enrolled face photos`;
  return review.effect(props.surface, "is_member", member.display_name);
}

const keysHint = computed(() => {
  const parts = memberVerdict.value ? ["number for a member"] : [];
  for (const v of otherVerdicts.value) {
    const key = VERDICT_KEYS[v.verdict];
    if (key) parts.push(`${key} for ${VERDICT_LABELS[v.verdict].toLowerCase()}`);
  }
  if (props.navigable) parts.push("arrows to move");
  return parts.join(", ");
});

onMounted(() => void review.load());
</script>
