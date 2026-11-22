import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";
import { withVueTs, vueTsConfigs } from "@vue/eslint-config-typescript";
import eslintConfigPrettier from "eslint-config-prettier";

// closes finding (no deterministic frontend tooling). The
// no-restricted-syntax selectors below replace tests/r4_bypass_guard.spec.js
// (auth-store ownership) and the negative half of
// tests/bundle.test.js (full-bundle echarts import) -- see those files'
// history before touching the messages, so the parity notes in the PR
// stay accurate.
//
// IMPORTANT: ESLint flat config does not merge array-valued rule options
// across matching config objects -- for a given rule name, the last matching
// block wins *entirely*, it does not append to earlier blocks. Every
// no-restricted-syntax and vue/no-restricted-syntax block below must therefore
// list every selector that applies to its file set; selectors are named
// constants below so the same selector object is reused (not retyped)
// everywhere it needs to apply.

const NO_USE_NOTIFY_IN_COMPOSABLE = {
  selector: "CallExpression[callee.name='useNotify']",
  message:
    "Composables take the view's notifier: accept { notify } and check it with " +
    "requireNotify(...). The view calls useNotify() and passes notify in.",
};

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

// EG-M13: DS v2 color restrictions (front-end rule 4).
// Hardcoded hex literals and hardcoded numeric rgb()/rgba() literals are banned
// outside the explicit color allowlist (styles/**, src/main.js, useAnnotationStyle.js,
// useIdentityColor.js, components/marauders/**). Vuetify's CSS-variable wrappers
// such as rgb(var(--v-theme-primary)) and rgba(var(--v-theme-primary), 0.12)
// remain permitted because they reference Vuetify theme tokens, not raw numbers.
const HEX_COLOR_PATTERN = "/#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\\b/";
const NUMERIC_RGB_PATTERN = "/\\brgba?\\s*\\(\\s*\\d/i";

const NO_HEX_COLOR_LITERAL = {
  selector: `Literal[value=${HEX_COLOR_PATTERN}]`,
  message:
    "Hardcoded hex color literal is forbidden outside the DS token allowlist (front-end rule 4). " +
    "Use a --cc-* token (var(--cc-*) or ccToken('--cc-*')) or a Vuetify theme color.",
};

const NO_HEX_COLOR_TEMPLATE = {
  selector: `TemplateElement[value.raw=${HEX_COLOR_PATTERN}]`,
  message:
    "Hardcoded hex color in a template literal is forbidden outside the DS token allowlist " +
    "(front-end rule 4). Use a --cc-* token or a Vuetify theme color.",
};

const NO_NUMERIC_RGB_LITERAL = {
  selector: `Literal[value=${NUMERIC_RGB_PATTERN}]`,
  message:
    "Hardcoded numeric rgb()/rgba() color is forbidden outside the DS token allowlist " +
    "(front-end rule 4). Use a --cc-* token or rgb(var(--v-theme-*)).",
};

const NO_NUMERIC_RGB_TEMPLATE = {
  selector: `TemplateElement[value.raw=${NUMERIC_RGB_PATTERN}]`,
  message:
    "Hardcoded numeric rgb()/rgba() color in a template literal is forbidden outside the DS " +
    "token allowlist (front-end rule 4). Use a --cc-* token or rgb(var(--v-theme-*)).",
};

const NO_HARDCODED_COLOR_SELECTORS = [
  NO_HEX_COLOR_LITERAL,
  NO_HEX_COLOR_TEMPLATE,
  NO_NUMERIC_RGB_LITERAL,
  NO_NUMERIC_RGB_TEMPLATE,
];

// EG-M13: Vue template restrictions (front-end rules 4, 11, 17).
const VUE_NO_SNACKBAR = {
  selector: "VElement[rawName='v-snackbar']",
  message:
    "Do not render a local <v-snackbar> (front-end rule 17). Use useNotify(); " +
    "CcSnackbarHost.vue is the sole snackbar renderer.",
};

const VUE_NO_BTN_TOGGLE = {
  selector: "VElement[rawName='v-btn-toggle']",
  message:
    "Do not use <v-btn-toggle> for pickers (front-end rule 11). Use CcSegmentedToggle " +
    "(RegionEditor.vue is the sole sanctioned icon-only exception).",
};

const VUE_NO_HEX_ATTR = {
  selector: `VAttribute[directive=false] > VLiteral[value=${HEX_COLOR_PATTERN}]`,
  message:
    "Hardcoded hex color in a template attribute is forbidden (front-end rule 4). " +
    "Use a --cc-* token or Vuetify theme color.",
};

const VUE_NO_NUMERIC_RGB_ATTR = {
  selector: `VAttribute[directive=false] > VLiteral[value=${NUMERIC_RGB_PATTERN}]`,
  message:
    "Hardcoded numeric rgb()/rgba() in a template attribute is forbidden (front-end rule 4). " +
    "Use a --cc-* token or rgb(var(--v-theme-*)).",
};

const VUE_NO_HEX_EXPR = {
  selector: `VExpressionContainer Literal[value=${HEX_COLOR_PATTERN}]`,
  message:
    "Hardcoded hex color in a template expression is forbidden (front-end rule 4). " +
    "Use a --cc-* token or Vuetify theme color.",
};

const VUE_NO_HEX_TEMPLATE_EXPR = {
  selector: `VExpressionContainer TemplateElement[value.raw=${HEX_COLOR_PATTERN}]`,
  message:
    "Hardcoded hex color in a template expression is forbidden (front-end rule 4). " +
    "Use a --cc-* token or Vuetify theme color.",
};

const VUE_NO_NUMERIC_RGB_EXPR = {
  selector: `VExpressionContainer Literal[value=${NUMERIC_RGB_PATTERN}]`,
  message:
    "Hardcoded numeric rgb()/rgba() in a template expression is forbidden (front-end rule 4). " +
    "Use a --cc-* token or rgb(var(--v-theme-*)).",
};

const VUE_NO_NUMERIC_RGB_TEMPLATE_EXPR = {
  selector: `VExpressionContainer TemplateElement[value.raw=${NUMERIC_RGB_PATTERN}]`,
  message:
    "Hardcoded numeric rgb()/rgba() in a template expression is forbidden (front-end rule 4). " +
    "Use a --cc-* token or rgb(var(--v-theme-*)).",
};

const VUE_NO_HARDCODED_COLOR_SELECTORS = [
  VUE_NO_HEX_ATTR,
  VUE_NO_NUMERIC_RGB_ATTR,
  VUE_NO_HEX_EXPR,
  VUE_NO_HEX_TEMPLATE_EXPR,
  VUE_NO_NUMERIC_RGB_EXPR,
  VUE_NO_NUMERIC_RGB_TEMPLATE_EXPR,
];

const MATERIAL_COLOR_VALUE_PATTERN =
  "/^(green|orange|purple|deep-purple|blue|red|grey|amber)(?:-.*)?$/";

const COLOR_ALLOWLIST_IGNORES = [
  "src/styles/**",
  "src/main.js",
  "src/composables/useAnnotationStyle.js",
  "src/composables/useIdentityColor.js",
  "src/components/marauders/**",
];

export default withVueTs(
  {
    scriptLangs: ["ts", "js"],
    rootDir: import.meta.dirname,
  },
  {
    ignores: [
      "dist/**",
      "src/generated/**",
      "coverage/**",
      "public/**",
      // Lint canary fixtures hold intentional violations exercised by
      // tests/architecture/lint_canary.spec.ts via ESLint's Node API.
      "tests/fixtures/lint_canary/**",
    ],
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
      // (AdminView, RoomsView,...); this project's convention is
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
    // typescript-eslint turns this off for type-checked files, but plain .js and .vue script
    // blocks have no compiler behind them. It catches a component calling `api` with no import.
    files: ["src/**/*.{js,vue}"],
    rules: { "no-undef": "error" },
  },
  {
    // EG-M13: pin clean-today runtime rules across all application source files.
    files: ["src/**/*.{js,ts,vue}"],
    rules: {
      // Front-end rule 10: native browser alert/confirm/prompt are forbidden; use useConfirm()/useNotify().
      "no-alert": "error",
    },
  },
  {
    // EG-M13 / front-end rule 23: all date/time formatting and local-clock reads
    // go through services/timezone.js so the app timezone is never bypassed.
    files: ["src/**/*.{js,ts,vue}"],
    ignores: ["src/services/timezone.js"],
    rules: {
      "no-restricted-properties": [
        "error",
        ...[
          "toLocaleString",
          "toLocaleDateString",
          "toLocaleTimeString",
          "getHours",
          "getMinutes",
          "getSeconds",
        ].map((property) => ({
          property,
          message:
            "Format and read dates through services/timezone.js (front-end rule 23), " +
            `not .${property}().`,
        })),
      ],
    },
  },
  {
    // The same mistake in a template: a name a classic setup() never returned. Nothing else
    // catches it, and it only fails when that line of the template runs.
    // Also enforces DS v2 class and material-color static attribute bans across all Vue templates.
    files: ["src/**/*.vue"],
    rules: {
      "vue/no-undef-properties": "error",
      "vue/no-restricted-class": ["error", "text-grey", "/^text-grey-/"],
      "vue/no-restricted-static-attribute": [
        "error",
        {
          key: "color",
          value: MATERIAL_COLOR_VALUE_PATTERN,
          message:
            "Vuetify material color names are forbidden (front-end rule 4). " +
            "Use DS semantic colors (primary, secondary, success, warning, error, info) or --cc-* tokens.",
        },
      ],
    },
  },
  {
    // EG-M13: Vue template restrictions for all non-exempt .vue files.
    files: ["src/**/*.vue"],
    ignores: [
      "src/components/CcSnackbarHost.vue",
      "src/components/eink/RegionEditor.vue",
      "src/components/marauders/**/*.vue",
    ],
    rules: {
      "vue/no-restricted-syntax": [
        "error",
        VUE_NO_SNACKBAR,
        VUE_NO_BTN_TOGGLE,
        ...VUE_NO_HARDCODED_COLOR_SELECTORS,
      ],
    },
  },
  {
    // CcSnackbarHost.vue is the sole sanctioned <v-snackbar> renderer.
    files: ["src/components/CcSnackbarHost.vue"],
    rules: {
      "vue/no-restricted-syntax": ["error", VUE_NO_BTN_TOGGLE, ...VUE_NO_HARDCODED_COLOR_SELECTORS],
    },
  },
  {
    // RegionEditor.vue is the sole sanctioned icon-only <v-btn-toggle> exception (EG-M13).
    files: ["src/components/eink/RegionEditor.vue"],
    rules: {
      "vue/no-restricted-syntax": ["error", VUE_NO_SNACKBAR, ...VUE_NO_HARDCODED_COLOR_SELECTORS],
    },
  },
  {
    // Marauder's Map components own their isolated parchment palette (color-allowlisted),
    // but still follow snackbar and button-toggle rules.
    files: ["src/components/marauders/**/*.vue"],
    rules: {
      "vue/no-restricted-syntax": ["error", VUE_NO_SNACKBAR, VUE_NO_BTN_TOGGLE],
    },
  },
  {
    // The Pinia auth store is the only owner of the API key storage key;
    // http.ts keeps a pre-wire localStorage fallback until main.js calls setApiKeyProvider.
    // All non-allowlisted src files also enforce DS v2 color-literal bans.
    files: ["src/**/*.{js,ts,vue}"],
    ignores: ["src/stores/auth.ts", "src/services/http.ts", ...COLOR_ALLOWLIST_IGNORES],
    rules: {
      "no-restricted-syntax": [
        "error",
        NO_REQUIRE_ECHARTS,
        NO_LOCALSTORAGE_API_KEY,
        ...NO_HARDCODED_COLOR_SELECTORS,
      ],
    },
  },
  {
    // auth.ts and http.ts own cc_api_key localStorage access, but still disallow hardcoded colors.
    files: ["src/stores/auth.ts", "src/services/http.ts"],
    rules: {
      "no-restricted-syntax": ["error", NO_REQUIRE_ECHARTS, ...NO_HARDCODED_COLOR_SELECTORS],
    },
  },
  {
    // Color-allowlisted non-composable files (Vuetify theme defs in main.js; Marauder's Map
    // isolated theme components) still enforce no-require-echarts and auth-store ownership.
    files: ["src/main.js", "src/components/marauders/**/*.{js,ts,vue}"],
    rules: {
      "no-restricted-syntax": ["error", NO_REQUIRE_ECHARTS, NO_LOCALSTORAGE_API_KEY],
    },
  },
  {
    // Front-end rule 19: feedback belongs to the view, so a composable never calls useNotify().
    files: ["src/composables/**/*.{js,ts}"],
    ignores: [
      "src/composables/useNotify.js",
      "src/composables/useAnnotationStyle.js",
      "src/composables/useIdentityColor.js",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        NO_REQUIRE_ECHARTS,
        NO_LOCALSTORAGE_API_KEY,
        NO_USE_NOTIFY_IN_COMPOSABLE,
        ...NO_HARDCODED_COLOR_SELECTORS,
      ],
    },
  },
  {
    // Color-allowlisted composables (photo annotation halos + deterministic identity palette)
    // still enforce no-require-echarts, auth-store ownership, and no-useNotify-in-composable.
    files: ["src/composables/useAnnotationStyle.js", "src/composables/useIdentityColor.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        NO_REQUIRE_ECHARTS,
        NO_LOCALSTORAGE_API_KEY,
        NO_USE_NOTIFY_IN_COMPOSABLE,
      ],
    },
  },
  {
    // Rule 17 (was tests/r4_bypass_guard.spec.js): components and views must go
    // through services/cts.js, never raw fetch(), inside the CTS admin surface.
    files: [
      "src/components/cts/**/*.vue",
      "src/views/admin/**/*.vue",
      "src/views/medical/**/*.vue",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        NO_REQUIRE_ECHARTS,
        NO_LOCALSTORAGE_API_KEY,
        NO_RAW_FETCH_IN_CTS_SURFACE,
        ...NO_HARDCODED_COLOR_SELECTORS,
      ],
    },
  },
  {
    // Established live-camera debug tracing convention (all "[cts_live]..."
    // prefixed) predates this milestone; keep it rather than delete working
    // trace points, but scope the console.debug allowance to just these files.
    // moved the tracing calls out of CTSLiveView.vue into the composables
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
