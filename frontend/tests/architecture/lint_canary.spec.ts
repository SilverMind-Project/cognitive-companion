import fs from "node:fs";
import path from "node:path";
import { ESLint } from "eslint";
import stylelint from "stylelint";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");
const CANARY_VUE_PATH = path.join(FRONTEND_ROOT, "tests/fixtures/lint_canary/CanaryViolations.vue");
const CANARY_VUE_SOURCE = fs.readFileSync(CANARY_VUE_PATH, "utf8");

describe("EG-M13 frontend lint canary (ESLint + Stylelint)", () => {
  it("ESLint fires every new EG-M13 rule on CanaryViolations.vue", async () => {
    const eslint = new ESLint({ cwd: FRONTEND_ROOT });
    // Lint under a virtual src/ path so every production files/ignores glob is exercised.
    const [result] = await eslint.lintText(CANARY_VUE_SOURCE, {
      filePath: path.join(FRONTEND_ROOT, "src/components/CanaryViolations.vue"),
    });

    const messages = result.messages;
    const ruleIds = new Set(messages.map((m) => m.ruleId));

    expect(ruleIds).toContain("no-alert");
    expect(ruleIds).toContain("no-restricted-properties");
    expect(ruleIds).toContain("no-restricted-syntax");
    expect(ruleIds).toContain("vue/no-restricted-class");
    expect(ruleIds).toContain("vue/no-restricted-static-attribute");
    expect(ruleIds).toContain("vue/no-restricted-syntax");

    // Verify each distinct restricted-syntax violation fired (not just one).
    const vueRestricted = messages
      .filter((m) => m.ruleId === "vue/no-restricted-syntax")
      .map((m) => m.message);
    expect(vueRestricted.some((m) => m.includes("<v-snackbar>"))).toBe(true);
    expect(vueRestricted.some((m) => m.includes("<v-btn-toggle>"))).toBe(true);
    expect(vueRestricted.some((m) => m.includes("hex color in a template attribute"))).toBe(true);
    expect(
      vueRestricted.some((m) => m.includes("numeric rgb()/rgba() in a template attribute")),
    ).toBe(true);
    expect(vueRestricted.some((m) => m.includes("hex color in a template expression"))).toBe(true);
    expect(
      vueRestricted.some((m) => m.includes("numeric rgb()/rgba() in a template expression")),
    ).toBe(true);

    const scriptRestricted = messages
      .filter((m) => m.ruleId === "no-restricted-syntax")
      .map((m) => m.message);
    expect(scriptRestricted.some((m) => m.includes("Hardcoded hex color"))).toBe(true);
    expect(scriptRestricted.some((m) => m.includes("Hardcoded numeric rgb()/rgba()"))).toBe(true);

    // Every restricted Date property fired.
    const propMsgs = messages
      .filter((m) => m.ruleId === "no-restricted-properties")
      .map((m) => m.message);
    for (const prop of [
      "toLocaleString",
      "toLocaleDateString",
      "toLocaleTimeString",
      "getHours",
      "getMinutes",
      "getSeconds",
    ]) {
      expect(propMsgs.some((m) => m.includes(`.${prop}()`))).toBe(true);
    }
  });

  it("ESLint respects sanctioned exceptions and permits Vuetify rgb(var(--v-theme-*))", async () => {
    const eslint = new ESLint({ cwd: FRONTEND_ROOT });

    // Vuetify theme CSS variable syntax is allowed in templates and scripts.
    const vuetifyThemeSample = `
<template>
  <div :style="{ color: accent, borderColor: 'rgb(var(--v-theme-primary))', background: 'rgba(var(--v-theme-primary), 0.12)' }" />
</template>
<script setup>
const accent = "rgba(var(--v-theme-success), 0.2)";
</script>
`;
    const [themeRes] = await eslint.lintText(vuetifyThemeSample, {
      filePath: path.join(FRONTEND_ROOT, "src/components/VuetifyThemeOk.vue"),
    });
    expect(themeRes.messages).toEqual([]);

    // CcSnackbarHost.vue may render <v-snackbar> (but still cannot render <v-btn-toggle>).
    const [snackbarHostRes] = await eslint.lintText(
      `<template><v-snackbar :model-value="true" /></template>`,
      { filePath: path.join(FRONTEND_ROOT, "src/components/CcSnackbarHost.vue") },
    );
    expect(snackbarHostRes.messages).toEqual([]);

    // RegionEditor.vue is the sanctioned icon-only <v-btn-toggle> exception.
    const [regionEditorRes] = await eslint.lintText(
      `<template><v-btn-toggle :model-value="0" /></template>`,
      { filePath: path.join(FRONTEND_ROOT, "src/components/eink/RegionEditor.vue") },
    );
    expect(regionEditorRes.messages).toEqual([]);

    // services/timezone.js may call toLocaleDateString().
    const [tzRes] = await eslint.lintText(
      `export const d = new Date().toLocaleDateString("en-CA");\n`,
      { filePath: path.join(FRONTEND_ROOT, "src/services/timezone.js") },
    );
    expect(tzRes.messages).toEqual([]);
  });

  it("Stylelint fires color-no-hex and numeric rgb/rgba bans while permitting Vuetify theme vars", async () => {
    const result = await stylelint.lint({
      code: CANARY_VUE_SOURCE,
      codeFilename: path.join(FRONTEND_ROOT, "src/components/CanaryViolations.vue"),
      cwd: FRONTEND_ROOT,
    });
    const warnings = result.results[0]?.warnings ?? [];
    const rules = new Set(warnings.map((w) => w.rule));

    expect(rules).toContain("color-no-hex");
    expect(rules).toContain("declaration-property-value-disallowed-list");

    // Vuetify's rgb(var(--v-theme-*)) and rgba(var(--v-theme-*), alpha) must pass cleanly.
    const cleanVuetifyStyle = `
<template><div class="ok" /></template>
<style scoped>
.ok {
  color: var(--cc-text-1);
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
}
</style>
`;
    const cleanRes = await stylelint.lint({
      code: cleanVuetifyStyle,
      codeFilename: path.join(FRONTEND_ROOT, "src/components/VuetifyThemeOk.vue"),
      cwd: FRONTEND_ROOT,
    });
    expect(cleanRes.results[0]?.warnings ?? []).toEqual([]);
  });

  it("ignores tests/fixtures/lint_canary/ during normal ESLint runs", async () => {
    const eslint = new ESLint({ cwd: FRONTEND_ROOT });
    expect(await eslint.isPathIgnored(CANARY_VUE_PATH)).toBe(true);
  });
});
