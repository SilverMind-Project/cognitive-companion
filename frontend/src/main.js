import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router/index.js";
import { initTimezone, getAppTimezone } from "./services/timezone.js";
import { api } from "./services/api.js";

// Vuetify
import "./styles/vuetify.scss";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import "@mdi/font/css/materialdesignicons.css";
import "@fontsource/kalam/latin-300.css";
import "@fontsource/kalam/latin-400.css";
import "@fontsource/kalam/latin-700.css";

// Global theme tokens. Mirrors docs/.vitepress/theme/custom.css so the
// marketing site and the in-product UI feel like the same product.
import "./styles/theme.css";
// Parchment token overrides for the ccMarauders Vuetify theme (M2).
import "./styles/marauders.css";

const vuetify = createVuetify({
  components,
  directives,
  defaults: {
    VCard: { rounded: "lg" },
    VBtn: { rounded: "pill" },
    VTextField: { variant: "outlined", density: "comfortable" },
    VTextarea: { variant: "outlined" },
    VSelect: { variant: "outlined", density: "comfortable" },
    VAutocomplete: { variant: "outlined", density: "comfortable" },
    VCombobox: { variant: "outlined", density: "comfortable" },
  },
  theme: {
    defaultTheme: localStorage.getItem("cc_theme") || "ccDark",
    themes: {
      ccDark: {
        dark: true,
        colors: {
          primary: "#0a84ff",
          secondary: "#5e5ce6",
          accent: "#bf5af2",
          error: "#ff453a",
          warning: "#ff9f0a",
          info: "#64d2ff",
          success: "#30d158",
          surface: "#1c1c1e",
          "surface-bright": "#2c2c2e",
          background: "#000000",
          "on-surface": "#f5f5f7",
          "on-background": "#f5f5f7",
        },
      },
      ccLight: {
        dark: false,
        colors: {
          primary: "#007aff",
          secondary: "#5856d6",
          accent: "#af52de",
          error: "#ff3b30",
          warning: "#ff9500",
          info: "#5ac8fa",
          success: "#34c759",
          surface: "#ffffff",
          "surface-bright": "#f2f2f7",
          background: "#f5f5f7",
          "on-surface": "#1d1d1f",
          "on-background": "#1d1d1f",
        },
      },
      ccMarauders: {
        dark: false, // parchment is a light surface; Vuetify computes on-colors from this
        colors: {
          background:      "#e9dcc0",
          surface:         "#f0e6cf",
          primary:         "#5b3a1a", // sepia ink
          secondary:       "#7a5230",
          error:           "#8a1c1c", // oxblood ink
          info:            "#3a4a6b",
          success:         "#3f5a36", // faded green ink
          warning:         "#9a6a1a",
          "on-background": "#3a2a16",
          "on-surface":    "#3a2a16",
          "on-primary":    "#f0e6cf",
        },
      },
    },
  },
});

async function bootstrap() {
  // Fetch app config from the backend before mounting so that all
  // timezone-aware formatters use the operator-configured timezone
  // (app.timezone in settings.yaml) rather than the browser's timezone.
  try {
    const info = await api.getAppInfo();
    initTimezone(info.timezone);
  } catch (e) {
    // Backend unreachable at load time; fall back to UTC (or the last value
    // cached in localStorage).  Timezone will be correct once the backend
    // comes back and the page is refreshed.
    console.warn("Failed to fetch app-info; timezone defaults to", getAppTimezone(), e);
  }

  const pinia = createPinia();
  const app = createApp(App);
  app.use(vuetify);
  app.use(pinia);
  app.use(router);
  app.mount("#app");
}

bootstrap();
