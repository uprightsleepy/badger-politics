import assert from "node:assert/strict";
import ts from "typescript";

/** A lib module as a data: URL, for the one test that needs a fresh copy of
 * a module and its import graph per case (city-district.test rewrites the
 * lookup import to an isolated instance). Everything else imports the .ts
 * files directly under Node's type stripping. */
export function compile(source) {
  const { outputText, diagnostics } = ts.transpileModule(source, {
    reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  assert.deepEqual(diagnostics, []);
  return outputText;
}

export const moduleUrl = (source, suffix = "") =>
  `data:text/javascript;base64,${Buffer.from(compile(source) + suffix).toString("base64")}`;
