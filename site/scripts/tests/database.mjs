import { useDatabase } from "../../src/lib/connection.ts";
import * as db from "../../src/lib/db.ts";

/** Point the site's own queries at a fixture connection. Results derived
 * from the previous connection are dropped with it. */
export function queries(conn) {
  useDatabase(conn);
  return db;
}
