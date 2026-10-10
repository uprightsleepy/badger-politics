/** A small map for each Assembly district: the district in Prairie, the
 * Senate district it sits inside outlined in Lake, and its neighbors in
 * Fog, framed on the Senate district. Read by /my-reps/ as an <img> once
 * the reader's districts are known, so the page never downloads the full
 * boundary set just to draw one picture. Drawn by lib/seatMap, which the
 * district pages share. */
import type { APIRoute } from "astro";
import { assemblySeatsWithMaps, seatMapSvg } from "../../../lib/seatMap";

export function getStaticPaths() {
  return assemblySeatsWithMaps().map((seat) => ({ params: { seat } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(`${seatMapSvg(params.seat!, "#F2C34F")}\n`, { headers: { "Content-Type": "image/svg+xml" } });
