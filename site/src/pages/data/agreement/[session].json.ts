/** One session's vote matrix for the compare page (lib/agreement). */
import type { APIRoute } from "astro";
import { builtSessions, voteMatrix } from "../../../lib/db";
import { personSlug } from "../../../lib/format";
import type { SessionVotes, VoteMatrix } from "../../../lib/wire";

export function getStaticPaths() {
  return builtSessions()
    .filter((s) => Object.keys(voteMatrix(s.id)).length > 0)
    .map((s) => ({ params: { session: s.id } }));
}

export const GET: APIRoute = ({ params }) => {
  const session = params.session!;
  const chambers: SessionVotes["chambers"] = {};
  for (const [chamber, m] of Object.entries(voteMatrix(session))) {
    chambers[chamber as "upper" | "lower"] = {
      rollCalls: m.rollCalls.map((e) => [e.id, e.date, e.identifier, e.motion]),
      members: m.members.map((p) => [personSlug(p.id), p.name, p.party, p.district]),
      votes: m.votes,
    } satisfies VoteMatrix;
  }
  const body: SessionVotes = { session, chambers };
  return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
};
