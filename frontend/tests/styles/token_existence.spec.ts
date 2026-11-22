import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "../..");
const SRC_DIR = path.join(FRONTEND_ROOT, "src");

const DEF_RE = /(--cc-[a-zA-Z0-9_-]+)\s*:/g;
const VAR_USE_RE = /var\(\s*(--cc-[a-zA-Z0-9_-]+)/g;
const TOKEN_HELPER_RE = /\bccToken\(\s*["'](--cc-[a-zA-Z0-9_-]+)["']\s*\)/g;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (path.relative(SRC_DIR, full) === "generated") continue;
      walk(full, out);
    } else if (/\.(vue|css|js|ts)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function collectDefinitions(source: string): Set<string> {
  return new Set([...source.matchAll(DEF_RE)].map((m) => m[1]));
}

function findUndefinedTokens(
  source: string,
  globalDefs: Set<string>,
): { usedCount: number; missing: string[] } {
  const localDefs = collectDefinitions(source);
  const missing: string[] = [];
  let usedCount = 0;

  for (const re of [VAR_USE_RE, TOKEN_HELPER_RE]) {
    for (const match of source.matchAll(re)) {
      const token = match[1];
      usedCount += 1;
      if (!globalDefs.has(token) && !localDefs.has(token)) {
        missing.push(token);
      }
    }
  }
  return { usedCount, missing };
}

describe("design token existence (--cc-*)", () => {
  const themeCss = fs.readFileSync(path.join(SRC_DIR, "styles/theme.css"), "utf8");
  const maraudersCss = fs.readFileSync(path.join(SRC_DIR, "styles/marauders.css"), "utf8");
  const globalDefs = new Set([
    ...collectDefinitions(themeCss),
    ...collectDefinitions(maraudersCss),
  ]);

  it("loads a non-empty global --cc-* token vocabulary from theme.css and marauders.css", () => {
    expect(globalDefs.size).toBeGreaterThan(50);
  });

  it("canary: flags an undefined --cc-* token in var() and ccToken()", () => {
    const sample = `
      .x { color: var(--cc-does-not-exist); background: var(--cc-surface); }
      const y = ccToken("--cc-also-missing");
    `;
    const result = findUndefinedTokens(sample, globalDefs);
    expect(result.missing).toEqual(["--cc-does-not-exist", "--cc-also-missing"]);
  });

  it("allows component-local --cc-* definitions within the same file", () => {
    const sample = `
      .card { --cc-local-accent: var(--cc-brand); border-color: var(--cc-local-accent); }
    `;
    const result = findUndefinedTokens(sample, globalDefs);
    expect(result.missing).toEqual([]);
  });

  it("every var(--cc-*) and ccToken('--cc-*') under src/ resolves to a defined token", () => {
    const files = walk(SRC_DIR);
    let totalUses = 0;
    const violations: string[] = [];

    for (const file of files) {
      const text = fs.readFileSync(file, "utf8");
      const { usedCount, missing } = findUndefinedTokens(text, globalDefs);
      totalUses += usedCount;
      for (const token of missing) {
        violations.push(`${path.relative(FRONTEND_ROOT, file)}: ${token}`);
      }
    }

    expect(totalUses).toBeGreaterThan(50);
    expect(violations).toEqual([]);
  });
});
