import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../../src/lib/paging.ts", import.meta.url), "utf8");
const { outputText, diagnostics } = ts.transpileModule(source, {
  reportDiagnostics: true,
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
assert.deepEqual(diagnostics, []);
const { yearPageStarts } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("year jumps are empty without votes", () => {
  assert.deepEqual(yearPageStarts([]), []);
});

for (const [n, page] of [[199, 1], [200, 2], [201, 2]]) {
  test(`a year after ${n} votes starts on page ${page}`, () => {
    assert.deepEqual(yearPageStarts([{ year: "2026", n }, { year: "2025", n: 1 }]), [
      { year: "2026", page: 1 },
      { year: "2025", page },
    ]);
  });
}

test("years can share a page and span several pages without changing input order", () => {
  const counts = Object.freeze([
    Object.freeze({ year: "2026", n: 199 }),
    Object.freeze({ year: "2025", n: 3 }),
    Object.freeze({ year: "2024", n: 400 }),
    Object.freeze({ year: "2023", n: 1 }),
  ]);
  assert.deepEqual(yearPageStarts(counts), [
    { year: "2026", page: 1 },
    { year: "2025", page: 1 },
    { year: "2024", page: 2 },
    { year: "2023", page: 4 },
  ]);
});

test("every year jump reaches its first vote with a supplied page size", () => {
  const counts = [{ year: "2026", n: 3 }, { year: "2025", n: 4 }, { year: "2024", n: 1 }];
  const votes = counts.flatMap(({ year, n }) =>
    Array.from({ length: n }, (_, i) => ({ id: `${year}-${i}`, year })),
  );
  const pages = [votes.slice(0, 3), votes.slice(3, 6), votes.slice(6, 9)];
  const jumps = yearPageStarts(counts, 3);
  assert.deepEqual(jumps, [
    { year: "2026", page: 1 },
    { year: "2025", page: 2 },
    { year: "2024", page: 3 },
  ]);
  for (const { year, page } of jumps) {
    assert.ok(pages[page - 1].some((vote) => vote.id === `${year}-0`));
    assert.ok(pages.slice(0, page - 1).flat().every((vote) => vote.year !== year));
  }
});
