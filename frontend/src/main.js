import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router/index.js";

// Vuetify
import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import "@mdi/font/css/materialdesignicons.css";

// Global theme tokens. Mirrors docs/.vitepress/theme/custom.css so the
// marketing site and the in-product UI feel like the same product.
import "./styles/theme.css";

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
    defaultTheme: "ccDark",
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
    },
  },
});

const pinia = createPinia();
const app = createApp(App);
app.use(vuetify);
app.use(pinia);
app.use(router);
app.mount("#app");
