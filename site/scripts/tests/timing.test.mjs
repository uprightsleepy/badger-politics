import assert from "node:assert/strict";
import { test } from "node:test";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const script = fileURLToPath(new URL("../../../.github/scripts/timed.sh", import.meta.url));
const linuxPath = (path) => path.replaceAll("\\", "/")
  .replace(/^([A-Za-z]):/, (_, drive) => `/mnt/${drive.toLowerCase()}`);
const runTimed = (dir, stage, code, ...args) => {
  // The production wrapper uses GNU time. Windows contributors run that
  // same wrapper under WSL, with their installed Windows Node via interop.
  if (process.platform === "win32") {
    return spawnSync("wsl.exe", ["--exec", "env", `RUNNER_TEMP=${linuxPath(dir)}`,
      "bash", linuxPath(script), stage, linuxPath(process.execPath), "-e", code, ...args],
    { encoding: "utf8" });
  }
  return spawnSync("bash", [script, stage, process.execPath, "-e", code, ...args],
    { env: { ...process.env, RUNNER_TEMP: dir }, encoding: "utf8" });
};

test("timing preserves a failing gate's exit code and retains stdout/stderr", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "bp-timing-test-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const result = runTimed(dir, "failed-gate",
    'console.log("checking"); console.error("broken link"); process.exit(7);');
  assert.equal(result.status, 7, result.stderr);
  const log = await readFile(join(dir, "badger-ci/failed-gate.log"), "utf8");
  assert.match(log, /checking/);
  assert.match(log, /broken link/);
  const timing = await readFile(join(dir, "badger-ci/failed-gate.time"), "utf8");
  assert.match(timing, /elapsed_seconds=/);
  assert.match(timing, /peak_rss_kib=/);
  assert.match(timing, /exit_status=7/);
});

test("timing passes arguments literally and preserves success", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "bp-timing-test-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const literal = "spaces and $(not-a-command)";
  const result = runTimed(dir, "passed-gate", "console.log(process.argv[1])", literal);
  assert.equal(result.status, 0, result.stderr);
  assert.equal((await readFile(join(dir, "badger-ci/passed-gate.log"), "utf8")).trim(), literal);
});
