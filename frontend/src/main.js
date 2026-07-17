import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router/index.js";
import { setApiKeyProvider } from "./services/http";
import { useAppConfigStore } from "./stores/appConfig";
import { useAuthStore } from "./stores/auth";

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
          primary: "#3F6B52", // sage-500
          secondary: "#C8704F", // terra-400
          error: "#BC5740", // brick-alert
          warning: "#C98A2E", // gold-notice
          info: "#4E7A8C", // blue-info
          success: "#2F8F5B", // green-care
          surface: "#FFFDF9", // surface-card
          background: "#FBF8F3", // surface-page
          "on-surface": "#2C2820", // stone-800
          "on-background": "#1D1A14", // stone-900
        },
      },
      ccMarauders: {
        dark: false,
        colors: {
          background: "#e9dcc0",
          surface: "#f0e6cf",
          primary: "#5b3a1a",
          secondary: "#7a5230",
          error: "#8a1c1c",
          info: "#3a4a6b",
          success: "#3f5a36",
          warning: "#9a6a1a",
          "on-background": "#3a2a16",
          "on-surface": "#3a2a16",
          "on-primary": "#f0e6cf",
        },
      },
    },
  },
});

async function bootstrap() {
  // Order matters. Pinia must be active before any store is touched, so it is installed first;
  // the API-key provider is repointed at the auth store before the first request goes out; and
  // app-info is still awaited before mount, so timezone-aware formatters render the
  // operator-configured timezone (app.timezone in settings.yaml) on the very first paint rather
  // than the browser's.
  const pinia = createPinia();
  const app = createApp(App);
  app.use(vuetify);
  app.use(pinia);
  app.use(router);

  setApiKeyProvider(() => useAuthStore().apiKey);

  // Never throws: a backend that is down at load time must not block the mount.
  await useAppConfigStore().bootstrap();

  app.mount("#app");
}

bootstrap();
