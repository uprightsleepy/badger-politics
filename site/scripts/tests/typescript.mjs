import assert from "node:assert/strict";
import ts from "typescript";

export function compile(source, { commonJS = false } = {}) {
  const { outputText, diagnostics } = ts.transpileModule(source, {
    reportDiagnostics: true,
    compilerOptions: {
      module: commonJS ? ts.ModuleKind.CommonJS : ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      ...(commonJS ? { esModuleInterop: true } : {}),
    },
  });
  assert.deepEqual(diagnostics, []);
  return outputText;
}

export const moduleUrl = (source, suffix = "") =>
  `data:text/javascript;base64,${Buffer.from(compile(source) + suffix).toString("base64")}`;
