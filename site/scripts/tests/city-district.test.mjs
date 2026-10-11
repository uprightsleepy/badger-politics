import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { moduleUrl } from "./typescript.mjs";

const lookupSource = await readFile(new URL("../../src/lib/lookup.ts", import.meta.url), "utf8");
const citySource = await readFile(new URL("../../src/lib/cityDistrict.ts", import.meta.url), "utf8");
let instance = 0;
const isolatedModuleUrl = (source) => moduleUrl(source, `\n// instance ${instance++}`);

const point = [-87.987654321, 43.012345678];
const rectangle = (x, y, width) => [
  [x - width, y - width], [x + width, y - width],
  [x + width, y + width], [x - width, y + width], [x - width, y - width],
];
const boundaries = {
  features: [{
    properties: { tenant: "synthetic-city", district: 7, slug: "unused", city: "Synthetic" },
    geometry: { type: "Polygon", coordinates: [rectangle(...point, 1e-10)] },
  }],
};

async function setup(t, response = async () => ({ json: async () => boundaries })) {
  const requests = [];
  const writes = [];
  const values = new Map([
    ["bp-city-district", '{"t":"old-city","d":2}'],
    ["bp-district", '{"ad":14,"sd":5}'],
  ]);
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { writes.push(["set", key, value]); values.set(key, value); },
    removeItem: (key) => { writes.push(["remove", key]); values.delete(key); },
  };
  const replace = (key, descriptor) => {
    const previous = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { configurable: true, ...descriptor });
    t.after(() => {
      if (previous) Object.defineProperty(globalThis, key, previous);
      else delete globalThis[key];
    });
  };
  replace("localStorage", { value: storage });
  for (const key of ["navigator", "document", "window"]) {
    replace(key, { get() { assert.fail(`${key} must not be accessed during city resolution`); } });
  }
  t.mock.method(globalThis, "fetch", async (...args) => {
    requests.push(args);
    assert.deepEqual(args, ["/data/local-districts.geojson"]);
    return response();
  });
  const lookup = isolatedModuleUrl(lookupSource);
  const store = new URL("../../src/lib/store.ts", import.meta.url).href;
  const city = await import(isolatedModuleUrl(citySource
    .replace('from "./lookup.ts"', `from ${JSON.stringify(lookup)}`)
    .replace('from "./store.ts"', `from ${JSON.stringify(store)}`)));
  assert.deepEqual(requests, [], "importing storage helpers must not fetch boundaries");
  assert.deepEqual(writes, [], "importing helpers must not alter saved districts");
  return { ...city, storage, values, writes, requests };
}

test("resolves the original precise longitude/latitude and saves only tenant and district", async (t) => {
  const city = await setup(t);
  assert.equal(await city.resolveCity(...point), undefined);
  assert.deepEqual(city.savedCityDistrict(), { t: "synthetic-city", d: 7 });
  assert.deepEqual(city.writes, [["set", "bp-city-district", '{"t":"synthetic-city","d":7}']]);
  assert.equal(city.values.get("bp-district"), '{"ad":14,"sd":5}');
  assert.equal(city.requests.length, 1);
});

test("a miss clears the previous city and reuses the cached boundary file", async (t) => {
  const city = await setup(t);
  await city.resolveCity(...point);
  await city.resolveCity(point[0] + 1, point[1]);
  assert.equal(city.savedCityDistrict(), null);
  assert.deepEqual(city.writes.at(-1), ["remove", "bp-city-district"]);
  assert.equal(city.requests.length, 1);
  assert.equal(city.values.get("bp-district"), '{"ad":14,"sd":5}');
});

test("rejected boundary retrieval clears a stale city and allows the next lookup to retry", async (t) => {
  let attempts = 0;
  const city = await setup(t, async () => {
    if (++attempts === 1) throw new Error("offline");
    return { json: async () => boundaries };
  });
  assert.equal(await city.resolveCity(...point), undefined);
  assert.equal(city.savedCityDistrict(), null);
  await city.resolveCity(...point);
  assert.deepEqual(city.savedCityDistrict(), { t: "synthetic-city", d: 7 });
  assert.equal(city.requests.length, 2);
});

test("an invalid boundary response clears the old city instead of keeping a stale result", async (t) => {
  const city = await setup(t, async () => ({ json: async () => { throw new SyntaxError("invalid JSON"); } }));
  assert.equal(await city.resolveCity(...point), undefined);
  assert.equal(city.savedCityDistrict(), null);
  assert.deepEqual(city.writes, [["remove", "bp-city-district"]]);
});

test("a point in a polygon hole clears the old city", async (t) => {
  const data = structuredClone(boundaries);
  data.features[0].geometry.coordinates = [rectangle(...point, 1), rectangle(...point, 0.1)];
  const city = await setup(t, async () => ({ json: async () => data }));
  await city.resolveCity(...point);
  assert.equal(city.savedCityDistrict(), null);
});

// blocked storage must not break the lookup that saves into it (lib/store)
test("a failed save leaves the existing city and the lookup still finishes", async (t) => {
  const city = await setup(t);
  city.storage.setItem = () => { throw new Error("storage unavailable"); };
  await city.resolveCity(...point);
  assert.equal(city.values.get("bp-city-district"), '{"t":"old-city","d":2}');
  assert.deepEqual(city.writes, []);
});

test("a failed clear after a lookup failure leaves the existing city and still finishes", async (t) => {
  const city = await setup(t, async () => { throw new Error("offline"); });
  city.storage.removeItem = () => { throw new Error("cannot remove saved city"); };
  await city.resolveCity(...point);
  assert.equal(city.values.get("bp-city-district"), '{"t":"old-city","d":2}');
});
