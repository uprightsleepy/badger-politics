/** Each district's close-up map for its own public page: an Assembly
 * district shaded inside its Senate district's outline, or a Senate
 * district filled with white lines between its three Assembly districts.
 * No Prairie: these maps aren't about the reader (docs/brand.md, "Maps").
 * Served as files so 132 pages don't each carry their paths inline. */
import type { APIRoute } from "astro";
import { hasSeatMap, seatMapSvg, SEAT_MAP_FILL } from "../../../../lib/seatMap";

export function getStaticPaths() {
  const seats = [
    ...Array.from({ length: 99 }, (_, i) => `assembly-${i + 1}`),
    ...Array.from({ length: 33 }, (_, i) => `senate-${i + 1}`),
  ];
  return seats.filter(hasSeatMap).map((seat) => ({ params: { seat } }));
}

export const GET: APIRoute = ({ params }) => {
  const seat = params.seat!;
  const fill = seat.startsWith("senate-") ? SEAT_MAP_FILL.senate : SEAT_MAP_FILL.assembly;
  return new Response(`${seatMapSvg(seat, fill)}\n`, { headers: { "Content-Type": "image/svg+xml" } });
};
