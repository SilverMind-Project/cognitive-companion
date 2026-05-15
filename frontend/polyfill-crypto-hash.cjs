/**
 * Polyfill for crypto.hash (Node.js 21.7+ / 20.12+).
 *
 * @vitejs/plugin-vue 6.x calls crypto.hash() from node:crypto. This function
 * does not exist in Node.js 18. Patching the cached CJS exports before any
 * ESM module loads ensures the polyfill is visible via
 * `import crypto from "node:crypto"` in the plugin.
 *
 * Loaded via --require in vitest poolOptions.forks.execArgv.
 */
"use strict";
const crypto = require("node:crypto");
if (typeof crypto.hash !== "function") {
  crypto.hash = function hash(algorithm, data, outputEncoding) {
    return crypto.createHash(algorithm).update(data).digest(outputEncoding ?? "hex");
  };
}
