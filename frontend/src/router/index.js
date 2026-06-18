import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "companion",
    component: () => import("../views/CompanionView.vue"),
  },
  {
    path: "/admin",
    component: () => import("../views/AdminView.vue"),
    children: [
      {
        path: "",
        name: "admin",
        redirect: "/admin/dashboard",
      },
      {
        path: "dashboard",
        name: "admin-dashboard",
        component: () => import("../views/admin/DashboardView.vue"),
      },
      {
        path: "rules",
        name: "admin-rules",
        component: () => import("../views/admin/RulesView.vue"),
      },
      {
        path: "rules/:id",
        name: "admin-rule-detail",
        component: () => import("../views/admin/RuleDetailView.vue"),
        props: true,
      },
      {
        path: "sensors",
        name: "admin-sensors",
        component: () => import("../views/admin/SensorsView.vue"),
      },
      {
        path: "rooms",
        name: "admin-rooms",
        component: () => import("../views/admin/RoomsView.vue"),
      },
      {
        path: "events",
        name: "admin-events",
        component: () => import("../views/admin/EventsView.vue"),
      },
      {
        path: "alerts",
        name: "admin-alerts",
        component: () => import("../views/admin/AlertsView.vue"),
      },
      {
        path: "interactive-responses",
        name: "admin-interactive-responses",
        component: () => import("../views/admin/InteractiveResponsesView.vue"),
      },
      {
        path: "persons",
        name: "admin-persons",
        component: () => import("../views/admin/PersonsView.vue"),
      },
      {
        path: "persons/:id",
        name: "admin-person-profile",
        component: () => import("../views/admin/PersonProfileView.vue"),
        props: true,
      },
      {
        path: "activities",
        name: "admin-activities",
        component: () => import("../views/admin/ActivitiesView.vue"),
      },
      {
        path: "timeline",
        redirect: { name: "admin-activities", query: { view: "timeline" } },
      },
      {
        path: "reports",
        name: "admin-reports",
        component: () => import("../views/admin/DailyReportsView.vue"),
      },
      {
        path: "workflows",
        redirect: "/admin/executions?tab=history",
      },
      {
        path: "executions",
        name: "admin-executions",
        component: () => import("../views/admin/ExecutionsView.vue"),
      },
      {
        path: "eink-templates",
        name: "admin-eink-templates",
        component: () => import("../views/admin/EInkTemplatesView.vue"),
      },
      {
        path: "knowledge/documents",
        name: "admin-knowledge-documents",
        component: () => import("../views/admin/KnowledgeDocumentsView.vue"),
      },
      {
        path: "knowledge/documents/:id",
        name: "admin-knowledge-document-edit",
        component: () => import("../views/admin/KnowledgeDocumentEditView.vue"),
        props: true,
      },
      {
        path: "knowledge/info-cards",
        name: "admin-info-cards",
        component: () => import("../views/admin/InfoCardsView.vue"),
      },
      {
        path: "knowledge/quizzes",
        name: "admin-quizzes",
        component: () => import("../views/admin/QuizzesView.vue"),
      },
      {
        path: "knowledge/interactions",
        name: "admin-knowledge-interactions",
        component: () => import("../views/admin/KnowledgeInteractionsView.vue"),
      },
      {
        path: "camera-media",
        name: "admin-camera-media",
        component: () => import("../views/admin/CameraMediaView.vue"),
      },

      // ── Guided Companion (M9) ────────────────────────────────────────────────
      {
        path: "routines",
        name: "admin-routines",
        component: () => import("../views/admin/RoutineListView.vue"),
      },
      {
        path: "routines/:id",
        name: "admin-routine-builder",
        component: () => import("../views/admin/RoutineBuilderView.vue"),
        props: true,
      },
      {
        path: "routines/:id/metrics",
        name: "admin-routine-metrics",
        component: () => import("../views/admin/RoutineMetricsView.vue"),
        props: true,
      },
      {
        path: "guided-sessions",
        name: "admin-guided-sessions",
        component: () => import("../views/admin/GuidedSessionListView.vue"),
      },
      {
        path: "guided-sessions/:id",
        name: "admin-guided-session-console",
        component: () => import("../views/admin/GuidedSessionConsoleView.vue"),
        props: true,
      },

      // ── Tracking workspace (U4) ──────────────────────────────────────────────
      {
        path: "tracking",
        name: "tracking-workspace",
        component: () => import("../views/tracking/TrackingWorkspace.vue"),
      },

      // ── Process Activity view (U5) ───────────────────────────────────────────
      {
        path: "activity",
        redirect: "/admin/executions?tab=live",
      },

      // ── Tracking - Setup (configuration tools, kept distinct from monitoring) ─
      {
        path: "cts/cameras",
        name: "cts-cameras",
        component: () => import("../views/admin/CTSCamerasView.vue"),
      },
      {
        path: "cts/calibration",
        name: "cts-calibration",
        component: () => import("../views/admin/CTSCalibrationView.vue"),
      },
      {
        path: "cts/privacy",
        name: "cts-privacy",
        component: () => import("../views/admin/CTSPrivacyView.vue"),
      },
      {
        path: "cts/adjacency",
        name: "cts-adjacency",
        component: () => import("../views/admin/CTSAdjacencyView.vue"),
      },
      {
        path: "cts/keyframes",
        name: "cts-keyframes",
        component: () => import("../views/admin/CTSKeyframesView.vue"),
      },

      // ── Superseded monitoring routes: redirect into workspace panels ──────────
      {
        path: "cts/dashboard",
        redirect: "/admin/tracking?panel=overview",
      },
      {
        path: "cts/signals",
        redirect: "/admin/tracking?panel=signals",
      },
      {
        path: "cts/live",
        redirect: "/admin/tracking?panel=live-floor",
      },
      {
        path: "cts/floor-plan",
        redirect: "/admin/tracking?panel=live-floor",
      },
      {
        path: "cts/people",
        redirect: "/admin/tracking?panel=people",
      },
      {
        path: "cts/presence",
        redirect: "/admin/tracking?panel=presence-timeline",
      },
      {
        path: "medical/signals",
        redirect: "/admin/tracking?panel=signals",
      },
      {
        path: "medical/reports/weekly",
        redirect: "/admin/tracking?panel=reports&period=week",
      },
      {
        path: "caregiver/presence/:personId?",
        redirect: (to) => {
          const q = { panel: "presence-timeline" };
          if (to.params.personId) q.person = to.params.personId;
          return { path: "/admin/tracking", query: q };
        },
      },
    ],
  },
];

export { routes };

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
