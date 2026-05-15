/**
 * Vitest setup: polyfill crypto.hash for Node.js < 21.7.0.
 *
 * crypto.hash(algorithm, data[, outputEncoding]) was added in Node.js 21.7.0 / 22.
 * @vitejs/plugin-vue 6.x uses it unconditionally. This shim lets tests run on
 * Node 18 (the current CI/dev environment) without upgrading the runtime.
 */
import { createHash } from "node:crypto";

if (typeof crypto.hash !== "function") {
  crypto.hash = function hash(algorithm, data, outputEncoding = "hex") {
    return createHash(algorithm).update(data).digest(outputEncoding);
  };
}
