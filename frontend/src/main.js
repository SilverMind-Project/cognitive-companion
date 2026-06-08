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
/* DS v2 fonts */
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/hanken-grotesk/700.css";
import "@fontsource/hanken-grotesk/800.css";
import "@fontsource/newsreader/400.css";
import "@fontsource/newsreader/400-italic.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/500-italic.css";
import "@fontsource/newsreader/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
/* Marauders map font (ccMarauders theme) */
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
    // DS: selection controls read sage (primary) when on, never neutral grey.
    VSwitch: { color: "primary", inset: true },
    VCheckbox: { color: "primary" },
    VRadioGroup: { color: "primary" },
  },
  theme: {
    defaultTheme: localStorage.getItem("cc_theme") === "ccMarauders" ? "ccMarauders" : "ccWarm",
    themes: {
      ccWarm: {
        dark: false,
        colors: {
          primary:          "#3F6B52",  // sage-500
          secondary:        "#C8704F",  // terra-400
          error:            "#BC5740",  // brick-alert
          warning:          "#C98A2E",  // gold-notice
          info:             "#4E7A8C",  // blue-info
          success:          "#2F8F5B",  // green-care
          surface:          "#FFFDF9",  // surface-card
          background:       "#FBF8F3",  // surface-page
          "on-surface":     "#2C2820",  // stone-800
          "on-background":  "#1D1A14",  // stone-900
        },
      },
      ccMarauders: {
        dark: false,
        colors: {
          background:      "#e9dcc0",
          surface:         "#f0e6cf",
          primary:         "#5b3a1a",
          secondary:       "#7a5230",
          error:           "#8a1c1c",
          info:            "#3a4a6b",
          success:         "#3f5a36",
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
