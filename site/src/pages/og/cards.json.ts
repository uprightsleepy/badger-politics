/** Share-card manifest: scripts/share-cards.mjs renders it to PNGs after
 * the build, then deletes it (lib/share). */
import type { APIRoute } from "astro";
import { shareCards } from "../../lib/share";

export const GET: APIRoute = () =>
  new Response(JSON.stringify(shareCards()), { headers: { "Content-Type": "application/json" } });
