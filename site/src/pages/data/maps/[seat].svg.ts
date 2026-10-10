/** A small map for each Assembly district: the district in Prairie, the
 * Senate district it sits inside outlined in Lake, and its neighbors in
 * Fog, framed on the Senate district. Read by /my-reps/ as an <img> once
 * the reader's districts are known, so the page never downloads the full
 * boundary set just to draw one picture.
 *
 * Paths come from the committed district shapes (the same projection the
 * district pages use). Wisconsin nests three Assembly districts in each
 * Senate district: Assembly 13, 14 and 15 make Senate 5. */
import type { APIRoute } from "astro";
import SHAPES from "../../../data/district-shapes.json";

const shapes = SHAPES as Record<string, string>;

type Box = { x0: number; y0: number; x1: number; y1: number };
const bbox = (path: string): Box => {
  const nums = path.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
  const b = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  for (let i = 0; i + 1 < nums.length; i += 2) {
    b.x0 = Math.min(b.x0, nums[i]);
    b.x1 = Math.max(b.x1, nums[i]);
    b.y0 = Math.min(b.y0, nums[i + 1]);
    b.y1 = Math.max(b.y1, nums[i + 1]);
  }
  return b;
};
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
const boxes = new Map(
  Object.keys(shapes)
    .filter((k) => k.startsWith("assembly-"))
    .map((k) => [k, bbox(shapes[k])]),
);

export function getStaticPaths() {
  return [...boxes.keys()]
    .filter((seat) => shapes[`senate-${Math.ceil(Number(seat.split("-")[1]) / 3)}`])
    .map((seat) => ({ params: { seat } }));
}

const ASPECT = 10 / 7;

export const GET: APIRoute = ({ params }) => {
  const seat = params.seat!;
  const ad = Number(seat.split("-")[1]);
  const sd = `senate-${Math.ceil(ad / 3)}`;
  const s = bbox(shapes[sd]);
  // frame the Senate district with room around it, at a fixed 10:7
  const pad = Math.max(s.x1 - s.x0, s.y1 - s.y0) * 0.18 + 1;
  let w = s.x1 - s.x0 + pad * 2;
  let h = s.y1 - s.y0 + pad * 2;
  if (w / h > ASPECT) h = w / ASPECT;
  else w = h * ASPECT;
  const cx = (s.x0 + s.x1) / 2;
  const cy = (s.y0 + s.y1) / 2;
  const view: Box = { x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2 };
  const r = (n: number) => Math.round(n * 10) / 10;
  const neighbors = [...boxes.entries()]
    .filter(([key, b]) => key !== seat && overlaps(b, view))
    .map(([key]) => `<path d="${shapes[key]}"/>`)
    .join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${r(view.x0)} ${r(view.y0)} ${r(w)} ${r(h)}">` +
    `<rect x="${r(view.x0)}" y="${r(view.y0)}" width="${r(w)}" height="${r(h)}" fill="#DCE6E4"/>` +
    `<g fill="#E6EBE7" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke">` +
    neighbors.replaceAll("<path ", '<path vector-effect="non-scaling-stroke" ') +
    `</g>` +
    `<path d="${shapes[seat]}" fill="#F2C34F" stroke="#18241F" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` +
    `<path d="${shapes[sd]}" fill="none" stroke="#0D5C63" stroke-width="3.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` +
    `</svg>\n`;
  return new Response(svg, { headers: { "Content-Type": "image/svg+xml" } });
};
