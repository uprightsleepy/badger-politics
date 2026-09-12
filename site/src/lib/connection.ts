/** The build's one SQLite connection and every cache bound to it. The
 * database is immutable during a build, so pages share prepared statements
 * and derived results. useDatabase() swaps the connection (tests hand in a
 * fixture) and drops everything derived from the previous one. */
import Database from "better-sqlite3";
import { resolve } from "node:path";

let db: Database.Database | undefined;
const stmts = new Map<string, Database.Statement>();
const caches: { clear(): void }[] = [stmts];

// Resolve from site/; the bundler may relocate this module's generated chunk.
const open = () =>
  new Database(resolve(process.env.WI_DATABASE_PATH ?? "../data/wi.sqlite"), {
    readonly: true,
    fileMustExist: true,
  });

export function useDatabase(conn: Database.Database): void {
  db = conn;
  for (const c of caches) c.clear();
}

/** Reuse prepared statements throughout the build. */
export const prep = (sql: string): Database.Statement => {
  let s = stmts.get(sql);
  if (!s) {
    s = (db ??= open()).prepare(sql);
    stmts.set(sql, s);
  }
  return s;
};

export const once = <T>(compute: () => T): (() => T) => {
  let value: T;
  let done = false;
  caches.push({ clear: () => { done = false; } });
  return () => {
    if (!done) {
      value = compute();
      done = true;
    }
    return value;
  };
};

export const memoBy = <K, V>(compute: (key: K) => V): ((key: K) => V) => {
  const cache = new Map<K, V>();
  caches.push(cache);
  return (key) => {
    if (!cache.has(key)) cache.set(key, compute(key));
    return cache.get(key)!;
  };
};

/** Enrichment tables are absent from older snapshots; their readers
 * degrade to "nothing" rather than failing the build. */
export const hasTable = memoBy(
  (name: string) =>
    !!prep("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?").get(name),
);
