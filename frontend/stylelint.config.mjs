/**
 * Stylelint configuration for Cognitive Companion frontend.
 *
 * Enforces Design System v2 color rules in Vue `<style>` blocks (EG-M13):
 * - No hex color literals (`color-no-hex`).
 * - No hardcoded numeric `rgb(...)` / `rgba(...)` color literals; Vuetify's
 *   CSS-variable theme wrappers (`rgb(var(--v-theme-*))`,
 *   `rgba(var(--v-theme-*), alpha)`) remain permitted per front-end rule 4.
 *
 * Allowlist: `src/styles/**` (DS token definitions), `src/components/marauders/**`
 * (isolated Marauder's Map theme), and `tests/fixtures/lint_canary/**` (tested
 * explicitly via Stylelint's Node API in `tests/architecture/lint_canary.spec.ts`).
 */
export default {
  extends: ["stylelint-config-standard-vue"],
  ignoreFiles: [
    "dist/**",
    "coverage/**",
    "src/generated/**",
    "src/styles/**",
    "src/components/marauders/**",
    "tests/fixtures/lint_canary/**",
  ],
  rules: {
    // EG-M13 DS color enforcement.
    "color-no-hex": true,
    "declaration-property-value-disallowed-list": {
      "/.*/": ["/\\brgba?\\s*\\(\\s*\\d/i"],
    },

    // Formatting and naming are owned by Prettier / Vuetify conventions;
    // keep stylelint focused on DS color and CSS correctness rules.
    "alpha-value-notation": null,
    "at-rule-empty-line-before": null,
    "color-function-alias-notation": null,
    "color-function-notation": null,
    "comment-empty-line-before": null,
    "custom-property-empty-line-before": null,
    "declaration-block-no-redundant-longhand-properties": null,
    "declaration-empty-line-before": null,
    "keyframes-name-pattern": null,
    "media-feature-range-notation": null,
    "no-descending-specificity": null,
    "property-no-vendor-prefix": null,
    "rule-empty-line-before": null,
    "selector-class-pattern": null,
    "selector-pseudo-class-no-unknown": [
      true,
      { ignorePseudoClasses: ["deep", "global", "slotted"] },
    ],
    "shorthand-property-no-redundant-values": null,
    "value-keyword-case": null,
  },
};
