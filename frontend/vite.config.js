import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 900,
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("@vue-flow")) return "vue-flow";
          if (id.includes("echarts") || id.includes("vue-echarts")) return "echarts";
          if (id.includes("vuetify")) return "vuetify";
          if (id.includes("@codemirror") || id.includes("@lezer")) return "codemirror";
        },
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./vitest.setup.js"],
    server: {
      // Vuetify ships component-level CSS imports. Node cannot load those, so any spec importing
      // a real Vuetify entry point (main.js) dies on VApp.css unless Vite transforms the package.
      deps: { inline: [/vuetify/] },
    },
  },
});
