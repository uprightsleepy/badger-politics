/** Close-up maps of one legislative district, framed on the Senate
 * district around it. Wisconsin nests three Assembly districts in each
 * Senate district (Assembly 13, 14 and 15 make Senate 5), so the Senate
 * district is the natural frame for both.
 *
 * Paths come from the committed district shapes (one projection for the
 * whole state). Pure string building: used by /data/maps/*.svg for My reps
 * and inlined on each district's own page. */
import SHAPES from "../data/district-shapes.json" with { type: "json" };

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
let boxCache: Map<string, Box> | undefined;
const boxes = () =>
  (boxCache ??= new Map(
    Object.keys(shapes)
      .filter((k) => k.startsWith("assembly-"))
      .map((k) => [k, bbox(shapes[k])]),
  ));

/** Assembly districts that have a shape and a Senate district around them. */
export const assemblySeatsWithMaps = (): string[] =>
  [...boxes().keys()].filter((seat) => shapes[`senate-${Math.ceil(Number(seat.split("-")[1]) / 3)}`]);

export const hasSeatMap = (seat: string): boolean => {
  const [house, n] = seat.split("-");
  const sd = house === "senate" ? seat : `senate-${Math.ceil(Number(n) / 3)}`;
  return !!shapes[seat] && !!shapes[sd];
};

const ASPECT = 10 / 7;

/** The map's SVG. `fill` is the focus district's color: Prairie when it
 * is the reader's own (My reps), Lake on a district's public page. For a
 * Senate district, its three Assembly districts are filled with white
 * lines between them. */
export const seatMapSvg = (seat: string, fill: string, attrs = ""): string => {
  const [house, n] = seat.split("-");
  const isSenate = house === "senate";
  const sd = isSenate ? seat : `senate-${Math.ceil(Number(n) / 3)}`;
  const focus = isSenate
    ? [3 * Number(n) - 2, 3 * Number(n) - 1, 3 * Number(n)].map((a) => `assembly-${a}`).filter((k) => shapes[k])
    : [seat];
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
  const r = (v: number) => Math.round(v * 10) / 10;
  const neighbors = [...boxes().entries()]
    .filter(([key, b]) => !focus.includes(key) && overlaps(b, view))
    .map(([key]) => `<path d="${shapes[key]}"/>`)
    .join("");
  const focusPaths = isSenate
    ? `<g fill="${fill}" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round">` +
      focus.map((k) => `<path vector-effect="non-scaling-stroke" d="${shapes[k]}"/>`).join("") +
      `</g>`
    : `<path d="${shapes[seat]}" fill="${fill}" stroke="#18241F" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${r(view.x0)} ${r(view.y0)} ${r(w)} ${r(h)}"${attrs}>` +
    `<rect x="${r(view.x0)}" y="${r(view.y0)}" width="${r(w)}" height="${r(h)}" fill="#DCE6E4"/>` +
    `<g fill="#E6EBE7" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke">` +
    neighbors.replaceAll("<path ", '<path vector-effect="non-scaling-stroke" ') +
    `</g>` +
    focusPaths +
    // the Senate outline is the union of its Assembly districts' outlines,
    // so on a Senate map the filled districts already show it
    (isSenate
      ? ""
      : `<path d="${shapes[sd]}" fill="none" stroke="#0D5C63" stroke-width="3.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`) +
    `</svg>`
  );
};

/** The whole state with one district filled: where the close-up is. */
export const stateLocatorSvg = (seat: string, fill: string, attrs = ""): string => {
  if (!shapes[seat]) return "";
  const b = bbox(shapes[seat]);
  const r = (v: number) => Math.round(v * 10) / 10;
  // a city district is a speck at this size: ring it so it can be found
  const ring = Math.max(b.x1 - b.x0, b.y1 - b.y0) < 24
    ? `<circle cx="${r((b.x0 + b.x1) / 2)}" cy="${r((b.y0 + b.y1) / 2)}" r="18" fill="none" stroke="${fill}" stroke-width="5"/>`
    : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${shapes._viewBox}"${attrs}>` +
    `<path d="${shapes._state}" fill="#E6EBE7" stroke="#848E88" stroke-width="0.8"/>` +
    `<path d="${shapes[seat]}" fill="${fill}" stroke="${fill}" stroke-width="1.5"/>` +
    ring +
    `</svg>`
  );
};
