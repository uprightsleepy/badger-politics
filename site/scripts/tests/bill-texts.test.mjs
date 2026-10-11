import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");
const DOCS = "https://docs.legis.wisconsin.gov";

test("a bill's texts pair each version's HTML with its PDF, then add offered amendments once", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec("INSERT INTO sessions (id, identifier) VALUES ('2025', '2025')");
  conn.exec("INSERT INTO bills (id, session_id, identifier) VALUES ('2025-ab1', '2025', 'AB 1')");
  const version = conn.prepare(
    "INSERT INTO bill_versions (bill_id, note, url, media_type) VALUES ('2025-ab1', ?, ?, ?)");
  version.run("Bill Text", `${DOCS}/document/proposaltext/2025/REG/AB1`, "text/html");
  version.run("Bill Text", `${DOCS}/document/proposaltext/2025/REG/AB1.pdf`, "application/pdf");
  version.run("Senate Amendment 1", `${DOCS}/document/amendments/2025/REG/AB1/sa1.pdf`, "application/pdf");
  version.run("Senate Amendment 1", `${DOCS}/document/amendments/2025/REG/AB1/sa1`, "text/html");
  const doc = conn.prepare("INSERT INTO bill_documents (bill_id, note, url) VALUES ('2025-ab1', ?, ?)");
  doc.run("AB 1: Senate Amendment 1", `${DOCS}/document/amendments/2025/REG/AB1/sa1`);
  doc.run("AB 1: Assembly Substitute Amendment 1", `${DOCS}/document/amendments/2025/REG/AB1/asa1`);
  doc.run("AB 1: Fiscal Estimate From DOA", `${DOCS}/document/fe/2025/REG/AB1/doa.pdf`);
  const db = queries(conn);
  assert.deepEqual(db.textsFor("2025-ab1"), [
    { label: "Bill Text", url: `${DOCS}/document/proposaltext/2025/REG/AB1`,
      pdf: `${DOCS}/document/proposaltext/2025/REG/AB1.pdf` },
    { label: "Senate Amendment 1", url: `${DOCS}/document/amendments/2025/REG/AB1/sa1`,
      pdf: `${DOCS}/document/amendments/2025/REG/AB1/sa1.pdf` },
    { label: "Assembly Substitute Amendment 1",
      url: `${DOCS}/document/amendments/2025/REG/AB1/asa1`, pdf: null },
  ]);
});
