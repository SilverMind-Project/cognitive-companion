import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";
import { withVueTs, vueTsConfigs } from "@vue/eslint-config-typescript";
import eslintConfigPrettier from "eslint-config-prettier";

// M19: closes finding C13 (no deterministic frontend tooling). The
// no-restricted-syntax selectors below replace tests/r4_bypass_guard.spec.js
// (Rule 17 / M18 auth-store ownership) and the negative half of
// tests/bundle.test.js (full-bundle echarts import) -- see those files'
// history before touching the messages, so the parity notes in the M19 PR
// stay accurate.
//
// IMPORTANT: ESLint flat config does not merge array-valued rule options
// across matching config objects -- for a given rule name, the last matching
// block wins *entirely*, it does not append to earlier blocks. Every
// no-restricted-syntax block below must therefore list every selector that
// applies to its file set; selectors are named constants below so the same
// selector object is reused (not retyped) everywhere it needs to apply.

const NO_LOCALSTORAGE_API_KEY = {
  selector:
    "CallExpression[callee.object.name='localStorage']" +
    "[callee.property.name=/^(get|set|remove)Item$/]" +
    "[arguments.0.value='cc_api_key']",
  message:
    "The API key lives in the Pinia auth store (src/stores/auth.ts); http.ts reads it " +
    "through setApiKeyProvider. Writing localStorage directly leaves the store's " +
    "reactive key stale, so the app keeps sending the old key until a reload.",
};

const NO_RAW_FETCH_IN_CTS_SURFACE = {
  selector: "CallExpression[callee.name='fetch']",
  message: "Rule 17 violation: raw fetch() in a CTS component/view. Use services/cts.js.",
};

const NO_REQUIRE_ECHARTS = {
  selector: "CallExpression[callee.name='require'][arguments.0.value='echarts']",
  message:
    "require('echarts') pulls in the full bundle. Import from echarts/core, " +
    "echarts/charts, echarts/components, or echarts/renderers subpaths instead.",
};

export default withVueTs(
  {
    scriptLangs: ["ts", "js"],
    rootDir: import.meta.dirname,
  },
  {
    ignores: ["dist/**", "src/generated/**", "coverage/**", "public/**"],
  },
  js.configs.recommended,
  pluginVue.configs["flat/recommended"],
  vueTsConfigs.recommended,
  eslintConfigPrettier,
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // The established convention (see the retired contracts.js): warnings and
      // errors surface real conditions in production; log/debug/info calls are
      // dev-time noise that should not ship.
      "no-console": ["warn", { allow: ["warn", "error"] }],
      // Vuetify + the admin surface use a lot of established single-word names
      // (AdminView, RoomsView, ...); this project's convention is
      // `<Domain><Kind>` which already reads as multi-word to a human, but the
      // rule's word-splitter only sees a single capitalized segment for some.
      // Audited against every current name in src/components + src/views:
      // none are single PascalCase words, so no ignores are needed.
      "vue/multi-word-component-names": "error",
      // Vuetify's data-table dynamic slot names are dotted (`#item.is_active`,
      // `#item.actions`); the rule's parser reads the dot as an (unsupported)
      // v-slot modifier and flags every one of them. This is a known
      // eslint-plugin-vue limitation against a Vuetify-standard convention,
      // not a real defect -- disabled rather than sprinkled with ~80 disables.
      "vue/valid-v-slot": "off",
      // Every chart module must import explicit echarts subpaths so Rollup can
      // tree-shake (was tests/bundle.test.js's "no full bundle import" checks).
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "echarts",
              message:
                "Import from echarts/core, echarts/charts, echarts/components, or " +
                "echarts/renderers subpaths so the bundle can tree-shake. See " +
                "src/components/charts/echarts.js for the registration pattern.",
            },
          ],
        },
      ],
      "no-restricted-syntax": ["error", NO_REQUIRE_ECHARTS],
      // Established convention throughout the codebase for "intentionally
      // unused" (destructured callback args, caught errors nobody inspects):
      // a leading underscore. The rule doesn't know that by default.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // M18: the Pinia auth store is the only owner of the API key storage key.
    // http.ts keeps a pre-wire localStorage fallback (see its own comment)
    // until main.js calls setApiKeyProvider.
    files: ["src/**/*.{js,ts,vue}"],
    ignores: ["src/stores/auth.ts", "src/services/http.ts"],
    rules: {
      "no-restricted-syntax": ["error", NO_REQUIRE_ECHARTS, NO_LOCALSTORAGE_API_KEY],
    },
  },
  {
    // Rule 17 (was tests/r4_bypass_guard.spec.js): components and views must go
    // through services/cts.js, never raw fetch(), inside the CTS admin surface.
    files: ["src/components/cts/**/*.vue", "src/views/admin/**/*.vue", "src/views/medical/**/*.vue"],
    rules: {
      "no-restricted-syntax": [
        "error",
        NO_REQUIRE_ECHARTS,
        NO_LOCALSTORAGE_API_KEY,
        NO_RAW_FETCH_IN_CTS_SURFACE,
      ],
    },
  },
  {
    // Established live-camera debug tracing convention (all "[cts_live] ..."
    // prefixed) predates this milestone; keep it rather than delete working
    // trace points, but scope the console.debug allowance to just these files.
    // M21 moved the tracing calls out of CTSLiveView.vue into the composables
    // that now own that state, so the allowance moves with them.
    files: [
      "src/views/admin/CTSLiveView.vue",
      "src/composables/useCtsWebSocket.js",
      "src/composables/useCtsLiveCameras.js",
      "src/composables/useLiveIdentityCache.js",
    ],
    rules: {
      "no-console": ["warn", { allow: ["warn", "error", "debug"] }],
    },
  },
  {
    files: ["tests/**/*.{js,ts}", "vitest.setup.js"],
    languageOptions: {
      globals: globals.vitest,
    },
  },
  {
    // The live pipeline feed normalizes whatever shape the /ws/pipeline socket
    // sends (run/node/edge payloads defined only by the backend event schema,
    // not by a shared type). Typing that properly is real design work outside
    // this tooling milestone's scope; scoped down here rather than silencing
    // the rule project-wide.
    files: ["src/stores/pipelineEvents.ts", "tests/stores/pipelineEvents.spec.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
