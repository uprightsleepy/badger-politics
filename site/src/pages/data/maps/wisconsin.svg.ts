/** Wisconsin's outline alone, in the district shapes' projection: the
 * locator behind each district page's small "where in the state" map,
 * one cached file instead of the outline inline on every page. */
import type { APIRoute } from "astro";
import { stateOutlineSvg } from "../../../lib/seatMap";

export const GET: APIRoute = () =>
  new Response(`${stateOutlineSvg()}\n`, { headers: { "Content-Type": "image/svg+xml" } });
