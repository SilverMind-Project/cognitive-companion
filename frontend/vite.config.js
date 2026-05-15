import { createRequire } from "node:module";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// crypto.hash was added in Node.js 21.7.0. @vitejs/plugin-vue 6.x calls it via
// `import crypto from "node:crypto"`. Patch the CJS module.exports object so that
// the ESM namespace (which holds a reference to the same object) has `hash`
// before the first transform. Must use createRequire to access the CJS cache.
{
  const req = createRequire(import.meta.url);
  const _crypto = req("node:crypto");
  if (typeof _crypto.hash !== "function") {
    _crypto.hash = (algorithm, data, outputEncoding = "hex") =>
      _crypto.createHash(algorithm).update(data).digest(outputEncoding);
  }
}

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
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./vitest.setup.js"],
    // Polyfill crypto.hash (Node 21.7+) before any ESM module loading in
    // the worker so @vitejs/plugin-vue 6.x transforms work on Node 18.
    execArgv: ["--require", "./polyfill-crypto-hash.cjs"],
  },
});
