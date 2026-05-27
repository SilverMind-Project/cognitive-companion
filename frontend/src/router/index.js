import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "companion",
    component: () => import("../views/CompanionView.vue"),
  },
  {
    path: "/admin",
    name: "admin",
    component: () => import("../views/AdminView.vue"),
    children: [
      {
        path: "",
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
        name: "admin-workflows",
        component: () => import("../views/admin/WorkflowsView.vue"),
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
      // CTS: Continuous Tracking System
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
        path: "cts/dashboard",
        name: "cts-dashboard",
        component: () => import("../views/admin/CTSDashboardView.vue"),
      },
      {
        path: "cts/signals",
        redirect: "/admin/alerts?source=cts",
      },
      {
        path: "cts/keyframes",
        name: "cts-keyframes",
        component: () => import("../views/admin/CTSKeyframesView.vue"),
      },
      {
        path: "cts/live",
        name: "cts-live",
        component: () => import("../views/admin/CTSLiveView.vue"),
      },
      {
        path: "cts/floor-plan",
        name: "cts-floor-plan",
        component: () => import("../views/admin/CTSFloorPlanView.vue"),
        meta: { title: "Floor Plan", icon: "mdi-floor-plan" },
      },
      {
        path: "cts/people",
        name: "CTSPeople",
        component: () => import("../views/admin/CTSPersonHypothesesView.vue"),
        meta: { title: "People & Hypotheses", icon: "mdi-account-group" },
      },
      {
        path: "cts/corrections",
        redirect: { name: "CTSPeople" },
      },
      {
        path: "cts/presence",
        name: "cts-presence",
        component: () => import("../views/admin/CTSPresenceView.vue"),
        meta: { title: "Presence Fusion", icon: "mdi-map-marker-radius" },
      },
      {
        path: "medical/signals",
        name: "SignalExplorer",
        component: () => import("../views/medical/SignalExplorerView.vue"),
        meta: { title: "Signal Explorer", icon: "mdi-chart-bar" },
      },
      {
        path: "medical/reports/weekly",
        name: "WeeklyReport",
        component: () => import("../views/medical/WeeklyReportView.vue"),
        meta: { title: "Weekly Report", icon: "mdi-file-document" },
      },
      {
        path: "caregiver/presence/:personId?",
        name: "PresenceTimeline",
        component: () => import("../views/caregiver/PresenceTimelineView.vue"),
        meta: { title: "Presence Timeline", icon: "mdi-timeline-clock" },
      },
    ],
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
