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

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: "dark",
    themes: {
      dark: {
        colors: {
          primary: "#6366f1",
          secondary: "#8b5cf6",
          accent: "#f59e0b",
          error: "#ef4444",
          warning: "#f59e0b",
          info: "#3b82f6",
          success: "#10b981",
          surface: "#1e1b2e",
          background: "#0f0e16",
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
