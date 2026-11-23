import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const SRC_DIR = path.resolve(import.meta.dirname, "../../src");

function vueFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return vueFiles(full);
    return entry.name.endsWith(".vue") ? [full] : [];
  });
}

/**
 * A client-side v-data-table computes its length from `items.length` and ignores
 * `items-length`. Given one server page, it shows that page as the whole list, so every
 * row past it is unreachable. A list paged by the server must use v-data-table-server.
 */
describe("server-paged tables use v-data-table-server", () => {
  it("no v-data-table receives items-length", () => {
    const offenders: string[] = [];
    for (const file of vueFiles(SRC_DIR)) {
      const source = fs.readFileSync(file, "utf8");
      // The opening tag of each client table. Quoted attribute values are skipped whole, so a
      // ">" inside one (an arrow function in a handler) does not end the tag early.
      for (const match of source.matchAll(/<v-data-table(?![-\w])(?:"[^"]*"|'[^']*'|[^>"'])*>/g)) {
        if (/[\s:]items-length=/.test(match[0])) offenders.push(path.relative(SRC_DIR, file));
      }
    }
    expect(offenders).toEqual([]);
  });
});
