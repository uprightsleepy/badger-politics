import { existsSync } from "node:fs";
import { join } from "node:path";

// the logos directory can't change mid-build; stat each entity at most once
const cache = new Map<string, boolean>();

export const logoExists = (entityId: number | string): boolean => {
  const id = String(entityId);
  let known = cache.get(id);
  if (known === undefined) {
    // resolve from the project root: import.meta.url points into the build bundle
    known = existsSync(join(process.cwd(), "public", "logos", `${id}.png`));
    cache.set(id, known);
  }
  return known;
};
