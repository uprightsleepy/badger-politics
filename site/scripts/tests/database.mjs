import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import vm from "node:vm";
import { compile } from "./typescript.mjs";

const require = createRequire(import.meta.url);
const source = await readFile(new URL("../../src/lib/db.ts", import.meta.url), "utf8");
const sentinels = await readFile(new URL("../../src/lib/sentinels.ts", import.meta.url), "utf8");
const constants = { exports: {} };
vm.runInNewContext(compile(sentinels, { commonJS: true }), { exports: constants.exports });

/** Run the actual site queries against an isolated fixture connection. */
export function queries(conn, code = source) {
  const module = { exports: {} };
  vm.runInNewContext(compile(code, { commonJS: true }), {
    exports: module.exports,
    process: { cwd: () => "/synthetic/site", env: {} },
    require: (name) => {
      if (name === "./sentinels") return constants.exports;
      if (name === "node:path") return require(name);
      assert.equal(name, "better-sqlite3");
      return function FixtureDatabase(_path, options) {
        assert.deepEqual({ ...options }, { readonly: true, fileMustExist: true });
        return conn;
      };
    },
  });
  return module.exports;
}
