import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compile } from "sass";

const themeCss = readFileSync(
  resolve(process.cwd(), "src/styles/theme.css"),
  "utf8",
);
const maraudersCss = readFileSync(
  resolve(process.cwd(), "src/styles/marauders.css"),
  "utf8",
);
const vuetifyScss = readFileSync(
  resolve(process.cwd(), "src/styles/vuetify.scss"),
  "utf8",
);
const compiledVuetifyCss = compile(
  resolve(process.cwd(), "src/styles/vuetify.scss"),
  {
    loadPaths: [resolve(process.cwd(), "node_modules")],
    style: "compressed",
  },
).css;

describe("Marauders typography theme", () => {
  it("uses the self-hosted Kalam handwriting family in Marauders mode", () => {
    expect(maraudersCss).toMatch(
      /\.v-theme--ccMarauders\s*\{[\s\S]*?--cc-font:\s*[\s\S]*?"Kalam"/,
    );
    expect(maraudersCss).toMatch(
      /\.v-theme--ccMarauders\s*\{[\s\S]*?font-family:\s*var\(--cc-font\)/,
    );
  });

  it("leaves the normal app font unchanged outside Marauders mode", () => {
    expect(themeCss).toMatch(/:root\s*\{[\s\S]*?--cc-font:\s*[\s\S]*?"Inter"/);
    expect(maraudersCss).not.toMatch(/\.v-theme--ccDark[\s\S]*?--cc-font/);
  });

  it("compiles Vuetify body and heading utilities against the shared font token", () => {
    expect(vuetifyScss).toMatch(/\$body-font-family:\s*var\(--cc-font\)/);
    expect(vuetifyScss).toMatch(/\$heading-font-family:\s*var\(--cc-font\)/);
    expect(compiledVuetifyCss).toMatch(
      /\.text-h4\{[^}]*font-family:var\(--cc-font\)/,
    );
    expect(compiledVuetifyCss).toMatch(
      /\.text-body-2\{[^}]*font-family:var\(--cc-font\)/,
    );
    expect(compiledVuetifyCss).toMatch(
      /\.text-md-h4\{[^}]*font-family:var\(--cc-font\)/,
    );
    expect(compiledVuetifyCss).not.toMatch(
      /\.text-(?:h4|body-2)\{[^}]*font-family:"Roboto"/,
    );
  });
});
