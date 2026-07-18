<template>
  <div>
    <v-card class="glass-card floor-plan-sidebar-card">
      <v-card-title class="floor-plan-card-title d-flex align-center">
        <v-icon start size="16" color="success">mdi-account-multiple</v-icon>
        Active Persons
        <v-chip class="ml-2" size="x-small" color="primary">{{ activePersons.length }}</v-chip>
      </v-card-title>
      <v-divider />
      <v-list density="compact" class="pa-1">
        <v-list-item
          v-for="person in activePersons"
          :key="person.gtId"
          class="person-card rounded-lg mb-1"
          :style="`border-left: 3px solid ${person.color}`"
        >
          <template #prepend>
            <div class="person-dot mr-3" :style="`background: ${person.color}`" />
          </template>
          <v-list-item-title class="text-body-2 font-weight-medium">
            {{ person.displayName }}
          </v-list-item-title>
          <v-list-item-subtitle class="text-caption">
            <span v-if="person.roomName">{{ person.roomName }}</span>
            <span v-else class="text-medium-emphasis">Room unknown</span>
            <template v-if="person.confidence > 0">
              &nbsp;·&nbsp;{{ Math.round(person.confidence * 100) }}%
            </template>
            <template v-if="person.posture"> &nbsp;·&nbsp;{{ person.posture }} </template>
          </v-list-item-subtitle>
          <template #append>
            <div class="d-flex flex-column align-end ga-1">
              <v-chip
                :color="person.calibrated ? 'success' : 'warning'"
                size="x-small"
                variant="tonal"
              >
                {{ person.calibrated ? "mapped" : "est." }}
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ formatAge(person.lastSeen) }}
              </span>
            </div>
          </template>
        </v-list-item>
        <v-list-item v-if="activePersons.length === 0" class="text-medium-emphasis text-caption">
          No active identified people
        </v-list-item>
      </v-list>
    </v-card>

    <!-- N4: Inferred presence badges -->
    <v-card v-if="worldInferredRooms.length > 0" class="glass-card floor-plan-sidebar-card mt-3">
      <v-card-title class="floor-plan-card-title">Inferred Presence</v-card-title>
      <v-divider />
      <v-card-text class="pa-2">
        <InferredPresenceBadge
          v-for="ir in worldInferredRooms"
          :key="`${ir.room_id}-${ir.person_id}`"
          :room-name="ir.room_name"
          :person-name="ir.person_id || ''"
          :since="ir.since"
          @dismiss="() => {}"
        />
      </v-card-text>
    </v-card>

    <!-- Snapshot status -->
    <v-card class="glass-card floor-plan-sidebar-card mt-3">
      <v-card-title class="floor-plan-card-title">Snapshot Status</v-card-title>
      <v-divider />
      <v-list density="compact" class="pa-1">
        <v-list-item class="rounded-lg">
          <template #prepend>
            <v-icon :color="worldStatusColor" size="16">{{ worldStatusIcon }}</v-icon>
          </template>
          <v-list-item-title class="text-caption">{{ worldStatusLabel }}</v-list-item-title>
          <v-list-item-subtitle class="text-caption text-medium-emphasis">
            {{ worldLastUpdate ? `Updated ${formatAge(worldLastUpdate)}` : "Waiting for snapshot" }}
          </v-list-item-subtitle>
        </v-list-item>
        <v-list-item class="rounded-lg">
          <template #prepend>
            <v-icon color="primary" size="16">mdi-account-group</v-icon>
          </template>
          <v-list-item-title class="text-caption"
            >{{ worldPhCount }} active PH(s)</v-list-item-title
          >
          <v-list-item-subtitle class="text-caption text-medium-emphasis">
            {{ worldPhMarkerCount }} on plan · {{ uncalibratedPhCount }} off-plan
          </v-list-item-subtitle>
        </v-list-item>
        <v-list-item class="rounded-lg">
          <template #prepend>
            <v-icon color="primary" size="16">mdi-door-open</v-icon>
          </template>
          <v-list-item-title class="text-caption"
            >{{ worldInferredRooms.length }} inferred-only room(s)</v-list-item-title
          >
          <v-list-item-subtitle class="text-caption text-medium-emphasis">
            {{ worldWsStatusLabel }}
          </v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-card>
  </div>
</template>

<script setup>
import InferredPresenceBadge from "@/components/cts/floor/InferredPresenceBadge.vue";

defineProps({
  activePersons: { type: Array, required: true },
  worldInferredRooms: { type: Array, required: true },
  worldStatusColor: { type: String, required: true },
  worldStatusIcon: { type: String, required: true },
  worldStatusLabel: { type: String, required: true },
  worldLastUpdate: { type: Number, default: null },
  worldPhCount: { type: Number, required: true },
  worldPhMarkerCount: { type: Number, required: true },
  uncalibratedPhCount: { type: Number, required: true },
  worldWsStatusLabel: { type: String, required: true },
});

function formatAge(ts) {
  if (!ts) return "";
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 5) return "now";
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}
</script>
