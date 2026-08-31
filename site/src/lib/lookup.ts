/** Address to legislative district, entirely in the reader's browser.
 *
 * Shared by /my-reps/ and the homepage so the lookup can be completed
 * wherever it is offered, rather than sending someone to another page to
 * finish what they started.
 *
 * The address goes to one place, the U.S. Census geocoder, and only to get
 * coordinates. The district itself is resolved here against the bundled
 * LTSB boundaries, which are authoritative for Wisconsin's 2024 maps.
 * Nothing is stored anywhere but this browser.
 */

import type { District } from "./district";
export type { District };

let boundaries: { features: { geometry: unknown; properties: District }[] } | null = null;

/** The 284 KB boundary file, fetched once per page. */
const loadBoundaries = async () => {
  if (!boundaries) {
    boundaries = await fetch("/data/wi-districts-2024.geojson").then((r) => r.json());
  }
  return boundaries!;
};

const pointInRing = (x: number, y: number, ring: number[][]): boolean => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
};

const pointInPolygon = (x: number, y: number, geom: any): boolean => {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  for (const poly of polys) {
    // a hit inside an outer ring still misses if it falls in a hole
    if (pointInRing(x, y, poly[0]) && !poly.slice(1).some((h: number[][]) => pointInRing(x, y, h))) {
      return true;
    }
  }
  return false;
};

/** Which district contains this point, or null if it is outside Wisconsin. */
export const districtAt = async (lng: number, lat: number): Promise<District | null> => {
  const data = await loadBoundaries();
  for (const f of data.features) {
    if (pointInPolygon(lng, lat, f.geometry)) return f.properties;
  }
  return null;
};

/** The Census geocoder sends no CORS headers but does support JSONP, which
 * keeps this working with no server of our own. The address reaches
 * census.gov and nowhere else. */
const geocode = (address: string): Promise<any> =>
  new Promise((resolve, reject) => {
    const cb = "bpGeo" + Date.now();
    const script = document.createElement("script");
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error("timeout"));
    }, 15000);
    function cleanup() {
      clearTimeout(timer);
      delete (window as any)[cb];
      script.remove();
    }
    (window as any)[cb] = (data: any) => {
      cleanup();
      resolve(data);
    };
    script.onerror = () => {
      cleanup();
      reject(new Error("load error"));
    };
    script.src =
      "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress" +
      "?benchmark=Public_AR_Current&format=jsonp&callback=" +
      cb +
      "&address=" +
      encodeURIComponent(address);
    document.head.appendChild(script);
  });

/** Address -> district, with the failure cases a reader needs told apart:
 * an address the geocoder cannot place, and a point outside Wisconsin. */
export const districtForAddress = async (
  address: string,
): Promise<{ district: District } | { error: string }> => {
  let data: any;
  try {
    data = await geocode(address);
  } catch {
    return { error: "The Census geocoder didn't respond. Try again in a moment, or use your location." };
  }
  const match = data?.result?.addressMatches?.[0];
  if (!match) {
    return { error: "Couldn't find that address. Try adding the city, or use your location instead." };
  }
  const district = await districtAt(match.coordinates.x, match.coordinates.y);
  if (!district) {
    return { error: "That address doesn't fall inside a Wisconsin legislative district." };
  }
  return { district };
};
