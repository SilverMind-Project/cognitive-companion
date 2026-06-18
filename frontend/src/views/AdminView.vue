<template>
  <v-app>
    <MaraudersImageFilterDefs />
    <MaraudersAdminBackground v-if="maraudersState.enabled" />
    <AdminParticleBackground v-else />
    <v-navigation-drawer
      :rail="!pinned"
      permanent
      :width="260"
      rail-width="68"
      expand-on-hover
      class="admin-nav"
    >
      <!-- Fixed brand header -->
      <template #prepend>
        <div class="d-flex align-center px-3 py-4 admin-brand">
          <div class="cc-brand-mark mr-3" aria-hidden="true">
            <img class="cc-brand-logo" src="/favicon.svg" alt="" />
          </div>
          <div class="brand-text">
            <div class="text-subtitle-1 font-weight-bold cc-gradient-text">Cognitive Companion</div>
          </div>
        </div>
      </template>

      <!-- Scrollable nav body -->
      <div class="nav-body" ref="navBodyRef" @scroll="updateScrollFade">
        <div class="nav-fade nav-fade--top" :class="{ 'is-visible': showTopFade }" aria-hidden="true"></div>

        <v-list density="comfortable" nav>
          <v-list-item rounded="lg" prepend-icon="mdi-home-variant-outline" title="Companion" to="/" />
          <v-divider class="my-2 mx-3" />
          <v-list-item rounded="lg" prepend-icon="mdi-view-dashboard-outline" title="Dashboard" to="/admin/dashboard" />

          <template v-for="section in navSections" :key="section.key">
            <v-list-subheader
              class="nav-section-header"
              :title="collapsedSections[section.key] ? 'Expand ' + section.title : 'Collapse ' + section.title"
              @click="toggleSection(section.key)"
            >
              <span class="nav-section-title">{{ section.title }}</span>
              <v-icon
                size="16"
                class="nav-section-chevron"
                :class="{ 'is-collapsed': collapsedSections[section.key] }"
              >mdi-chevron-down</v-icon>
            </v-list-subheader>

            <v-list-item
              v-for="item in section.items"
              v-show="!collapsedSections[section.key]"
              :key="item.to"
              rounded="lg"
              :prepend-icon="item.icon"
              :title="item.title"
              :to="item.to"
            />
          </template>
        </v-list>

        <div class="nav-fade nav-fade--bottom" :class="{ 'is-visible': showBottomFade }" aria-hidden="true"></div>
      </div>

      <!-- Fixed footer: pin toggle -->
      <template #append>
        <div class="nav-footer">
          <v-divider class="mx-3 mb-1" />
          <v-list density="compact" nav>
            <v-list-item
              rounded="lg"
              :prepend-icon="pinned ? 'mdi-pin-off-outline' : 'mdi-pin-outline'"
              :title="pinned ? 'Auto hide' : 'Keep open'"
              @click="togglePin"
            />
          </v-list>
        </div>
      </template>
    </v-navigation-drawer>

    <v-app-bar flat>
      <v-app-bar-title>
        <span class="text-h6 font-weight-bold">Caregiver Console</span>
      </v-app-bar-title>
      <v-spacer />
      <v-btn
        v-if="alertCount > 0"
        size="small"
        variant="tonal"
        :color="alertSeverity"
        prepend-icon="mdi-alert-circle"
        class="mr-3"
        :title="alertTooltip"
        @click="$router.push('/admin/alerts')"
      >
        {{ alertCount }} alert{{ alertCount !== 1 ? 's' : '' }}
      </v-btn>
      <MaraudersToggle />
      <v-btn icon="mdi-refresh" variant="text" title="Reload config" @click="reloadConfig" />
      <v-btn size="small" variant="tonal" class="mx-2" @click="showKeyDialog = true">
        <v-icon start>mdi-key-variant</v-icon>
        API Key
      </v-btn>
    </v-app-bar>

    <v-main>
      <v-container fluid class="px-6 py-6 cc-main-container">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </v-container>
    </v-main>

    <!-- API Key dialog -->
    <v-dialog v-model="showKeyDialog" max-width="440">
      <v-card>
        <v-card-title>Set API Key</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="apiKeyInput"
            label="API Key"
            :type="showKey ? 'text' : 'password'"
            hide-details
            :append-inner-icon="showKey ? 'mdi-eye-off' : 'mdi-eye'"
            @click:append-inner="showKey = !showKey"
          />
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="showKeyDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="saveApiKey">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </v-app>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from "vue";
import { api } from "../services/api.js";
import { cts } from "../services/cts.js";
import { useMaraudersMode } from "../composables/useMaraudersMode.js";
import AdminParticleBackground from "../components/common/AdminParticleBackground.vue";
import MaraudersAdminBackground from "../components/marauders/MaraudersAdminBackground.vue";
import MaraudersImageFilterDefs from "../components/marauders/MaraudersImageFilterDefs.vue";
import MaraudersToggle from "../components/marauders/MaraudersToggle.vue";

const { state: maraudersState } = useMaraudersMode();

const showKeyDialog = ref(false);
const showKey = ref(false);
const apiKeyInput = ref(localStorage.getItem("cc_api_key") || "");
const snack = ref(false);
const snackText = ref("");
const snackColor = ref("success");

function saveApiKey() {
  api.setApiKey(apiKeyInput.value);
  showKeyDialog.value = false;
  notify("API key saved");
}

async function reloadConfig() {
  try {
    await api.reloadConfig();
    notify("Config reloaded");
  } catch (e) {
    notify(e.message, "error");
  }
}

// Alert ticker (Phase 7)
const alertCount = ref(0);
const alertSeverity = ref("warning");
const alertTooltip = ref("");
let _alertTimer = null;

async function pollAlerts() {
  try {
    const data = await cts.getUnacknowledgedCount();
    alertCount.value = data.count || 0;
    if (data.signals && data.signals.length > 0) {
      const top = data.signals[0];
      alertTooltip.value = `${top.kind || top.signal_kind}: ${top.identity_id || top.person_id}`;
      alertSeverity.value = top.severity === "emergency" ? "error" : "warning";
    }
  } catch {
    alertCount.value = 0;
  }
}

// ── Navigation drawer enhancements ──

// Pin toggle
const pinned = ref(localStorage.getItem("cc_nav_pinned") === "true");

function togglePin() {
  pinned.value = !pinned.value;
  localStorage.setItem("cc_nav_pinned", pinned.value.toString());
  nextTick(() => updateScrollFade());
}

// Collapsible sections
function loadCollapsedState() {
  try {
    return JSON.parse(localStorage.getItem("cc_nav_collapsed") || "{}");
  } catch {
    return {};
  }
}

function saveCollapsedState() {
  localStorage.setItem("cc_nav_collapsed", JSON.stringify(collapsedSections));
}

const collapsedSections = reactive(loadCollapsedState());

function toggleSection(key) {
  collapsedSections[key] = !collapsedSections[key];
  saveCollapsedState();
  nextTick(() => updateScrollFade());
}

const navSections = [
  {
    key: "automation",
    title: "Automation",
    items: [
      { to: "/admin/rules",     icon: "mdi-shield-check-outline", title: "Rules"     },
      { to: "/admin/executions", icon: "mdi-sitemap-outline",      title: "Executions" },
      { to: "/admin/events",    icon: "mdi-calendar-text-outline", title: "Events"    },
    ],
  },
  {
    key: "infrastructure",
    title: "Infrastructure",
    items: [
      { to: "/admin/sensors", icon: "mdi-access-point", title: "Sensors" },
      { to: "/admin/rooms", icon: "mdi-floor-plan", title: "Rooms" },
      { to: "/admin/camera-media", icon: "mdi-camera-burst", title: "Camera Media" },
      { to: "/admin/eink-templates", icon: "mdi-image-edit-outline", title: "E-Ink Templates" },
    ],
  },
  {
    key: "tracking",
    title: "Tracking",
    items: [
      { to: "/admin/tracking", icon: "mdi-view-dashboard-variant-outline", title: "Tracking Workspace" },
    ],
  },
  {
    key: "tracking-setup",
    title: "Tracking - Setup",
    items: [
      { to: "/admin/cts/cameras",     icon: "mdi-cctv",                   title: "Cameras"         },
      { to: "/admin/cts/calibration", icon: "mdi-crosshairs-gps",         title: "Calibration"     },
      { to: "/admin/cts/privacy",     icon: "mdi-eye-off-outline",         title: "Privacy Zones"   },
      { to: "/admin/cts/adjacency",   icon: "mdi-graph-outline",           title: "Camera Adjacency"},
      { to: "/admin/cts/keyframes",   icon: "mdi-image-search-outline",    title: "Keyframes"       },
    ],
  },
  {
    key: "knowledge",
    title: "Knowledge",
    items: [
      { to: "/admin/knowledge/documents", icon: "mdi-file-document-outline", title: "Documents" },
      { to: "/admin/knowledge/info-cards", icon: "mdi-card-text-outline", title: "Info Cards" },
      { to: "/admin/knowledge/quizzes", icon: "mdi-help-box-outline", title: "Quizzes" },
      { to: "/admin/knowledge/interactions", icon: "mdi-chart-bar", title: "Interactions" },
    ],
  },
  {
    key: "people",
    title: "People",
    items: [
      { to: "/admin/persons", icon: "mdi-account-group-outline", title: "Members & Enrollment" },
      { to: "/admin/activities", icon: "mdi-run", title: "Activities" },
      { to: "/admin/reports", icon: "mdi-chart-box", title: "Daily Reports" },
      { to: "/admin/alerts", icon: "mdi-alert-circle-outline", title: "Alerts" },
    ],
  },
  {
    key: "guided-companion",
    title: "Guided Companion",
    items: [
      { to: "/admin/routines", icon: "mdi-clipboard-list-outline", title: "Routines" },
      { to: "/admin/guided-sessions", icon: "mdi-monitor-eye", title: "Sessions" },
    ],
  },
];

// Scroll fade detection
const navBodyRef = ref(null);
const showTopFade = ref(false);
const showBottomFade = ref(false);
let _navResizeObserver = null;

function updateScrollFade() {
  const el = navBodyRef.value;
  if (!el) return;
  showTopFade.value = el.scrollTop > 4;
  showBottomFade.value = el.scrollTop + el.clientHeight < el.scrollHeight - 4;
}

onMounted(() => {
  pollAlerts();
  _alertTimer = setInterval(pollAlerts, 30000);
  window.addEventListener("cc:alerts-changed", pollAlerts);

  nextTick(() => updateScrollFade());
  if (navBodyRef.value) {
    _navResizeObserver = new ResizeObserver(() => updateScrollFade());
    _navResizeObserver.observe(navBodyRef.value);
  }
});

onBeforeUnmount(() => {
  clearInterval(_alertTimer);
  window.removeEventListener("cc:alerts-changed", pollAlerts);
  if (_navResizeObserver) _navResizeObserver.disconnect();
});

function notify(text, color = "success") {
  snackText.value = text;
  snackColor.value = color;
  snack.value = true;
}

onMounted(() => {
  if (!localStorage.getItem("cc_api_key")) {
    showKeyDialog.value = true;
  }
});
</script>

<style scoped>
/* ── Drawer flex layout ── */

/* Pin drawer to viewport — Vuetify defaults to position:absolute which scrolls with the page */
.admin-nav {
  position: fixed !important;
  top: 0 !important;
  bottom: 0 !important;
  height: auto !important;
}

.admin-nav :deep(.v-navigation-drawer__content) {
  flex: 1 1 0;
  min-height: 0;
}

/* ── Brand header ── */

.admin-brand {
  min-height: 56px;
}

.cc-brand-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cc-brand-logo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-text {
  white-space: nowrap;
  overflow: hidden;
  opacity: 1;
  transition: opacity 0.18s ease;
}

.v-navigation-drawer--rail:not(.v-navigation-drawer--is-hovering) .brand-text {
  opacity: 0;
}

/* ── Scroll body ── */

.nav-body {
  position: relative;
  height: 100%;
  overflow-y: auto;
}

/* ── Scroll fade indicators ── */

.nav-fade {
  position: sticky;
  left: 0;
  right: 0;
  height: 28px;
  pointer-events: none;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.35s ease;
}

.nav-fade--top {
  top: 0;
  background: linear-gradient(to bottom, var(--cc-drawer-glass), transparent);
}

.nav-fade--bottom {
  bottom: 0;
  background: linear-gradient(to top, var(--cc-drawer-glass), transparent);
}

.nav-fade.is-visible {
  opacity: 1;
}

/* ── Collapsible section headers ── */

.nav-section-header {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 12px;
  border-radius: var(--cc-radius-sm);
  transition: background-color 0.15s ease;
  margin: 0 8px;
}

.nav-section-header:hover {
  background-color: var(--cc-surface-2);
}

.nav-section-title {
  flex: 1;
}

.nav-section-chevron {
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  color: var(--cc-text-3);
}

.nav-section-chevron.is-collapsed {
  transform: rotate(-90deg);
}

/* ── Footer ── */

.nav-footer {
  padding-bottom: 4px;
}


</style>
