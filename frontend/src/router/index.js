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
        path: "persons",
        name: "admin-persons",
        component: () => import("../views/admin/PersonsView.vue"),
      },
      {
        path: "activities",
        name: "admin-activities",
        component: () => import("../views/admin/ActivitiesView.vue"),
      },
      {
        path: "timeline",
        name: "admin-timeline",
        component: () => import("../views/admin/PersonTimelineView.vue"),
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
        path: "camera-media",
        name: "admin-camera-media",
        component: () => import("../views/admin/CameraMediaView.vue"),
      },
    ],
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
