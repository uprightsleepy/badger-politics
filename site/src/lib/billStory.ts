/** A bill's record, retold in plain words: where it is, who has it now,
 * and what happens next. Everything here is derived from the official
 * action history the page already loads; nothing is guessed, and anything
 * this module does not recognize falls back to the Legislature's own
 * wording. See docs/brand.md ("Status wording") for the rules. */
import SCHEDULE from "../data/session-schedule.json" with { type: "json" };
import { chamberName, fmtDate } from "./format.ts";
import type { TermId } from "./glossary.ts";

export interface StoryAction {
  date: string;
  chamber: string | null;
  description: string;
  classification: string | null;
}

export interface StoryBill {
  session_id: string;
  chamber: string | null;
  classification: string | null;
  status: string | null;
}

const HEARING_RE = /\bpublic hearing held\b/i;
const EXEC_RE = /\bexecutive (?:session held|action taken)\b/i;
const REPORT_RE =
  /^report (passage|adoption|concurrence|introduction and adoption)(?: as amended)? recommended by (.+?)(?:,\s*ayes,?\s*(\d+),?\s*noes,?\s*(\d+))?\s*$/i;
const REFERRAL_RE = /referred to (?:the )?(.+?)\s*$/i;
const SJR1_RE = /failed to (?:pass|concur in|adopt) pursuant to senate joint resolution 1/i;
const TALLY_RE = /ayes,?\s*(\d+),?\s*noes,?\s*(\d+)/i;
const ACT_RE = /(\d{4}) Wisconsin Act (\d+)/i;
const OVERRIDE_RE = /notwithstanding the objections of the governor/i;
const PRESENTED_RE = /^presented to the governor/i;
const SIGNED_RE = /approved by the governor/i;
const VETOED_RE = /vetoed by the governor/i;

const classes = (a: StoryAction): string[] => (a.classification ?? "").split(",").filter(Boolean);
const has = (a: StoryAction, cls: string) => classes(a).includes(cls);
const tally = (text: string): { yes: number; no: number } | null => {
  const m = TALLY_RE.exec(text);
  return m ? { yes: Number(m[1]), no: Number(m[2]) } : null;
};

/** "Children and Families" referred in the Assembly ->
 * "Assembly Committee on Children and Families". Joint committees keep
 * their own name. Floor calendars are scheduling, not committees. */
export const committeeFromReferral = (description: string, chamber: string | null): string | null => {
  const m = REFERRAL_RE.exec(description);
  if (!m) return null;
  // "... on Education pursuant to Senate Rule 46(2)(c)" or "... by
  // Committee on Senate Organization": keep only the committee's name
  let name = m[1]
    .replace(/\.$/, "")
    .replace(/\s+pursuant to\b.*$/i, "")
    .replace(/\s+by (?:the )?committee on\b.*$/i, "");
  if (/^calendar\b/i.test(name)) return null;
  if (/^joint committee/i.test(name)) return name.replace(/^joint committee/i, "Joint Committee");
  name = name.replace(/^committee on /i, "");
  return `${chamberName(chamber)} Committee on ${name}`;
};

/** The schedule only covers one biennium. Sessions before it are over;
 * sessions after it are ones we have no calendar for yet, so we never call
 * them over. */
const scheduledSession = (sessionId: string) => sessionId === SCHEDULE.session.slice(0, 4);
const scheduleYear = Number(SCHEDULE.session_start.slice(0, 4));
const before = (sessionId: string) => Number(sessionId.slice(0, 4)) < scheduleYear;
const after = (sessionId: string) => Number(sessionId.slice(0, 4)) > scheduleYear + 1;

/** The last day of the session's final general-business floorperiod, when
 * the schedule records it. */
export const lastVotingDay = (sessionId: string): string | null => {
  if (!scheduledSession(sessionId)) return null;
  const final = SCHEDULE.floorperiods.find((f) => "label" in f && /final general-business/i.test(String(f.label)));
  return final?.end ?? null;
};

/** Has the session stopped moving bills? Past biennia have. The current
 * regular session has once its last general-business day passes. A
 * special session of the current biennium can meet any time until the
 * biennium ends. */
export const sessionClosed = (sessionId: string, today: string): boolean => {
  if (before(sessionId)) return true;
  if (after(sessionId)) return false;
  if (scheduledSession(sessionId)) {
    const last = lastVotingDay(sessionId);
    return last != null && today > last;
  }
  return today > SCHEDULE.session_end;
};

/** Can lawmakers still take up a veto? Overrides get their own floorperiod
 * after general business ends, so this window closes later. */
export const vetoWindowClosed = (sessionId: string, today: string): boolean => {
  if (before(sessionId)) return true;
  if (after(sessionId)) return false;
  if (scheduledSession(sessionId)) {
    const last = SCHEDULE.floorperiods.map((f) => f.end).sort().at(-1);
    return last != null && today > last;
  }
  return today > SCHEDULE.session_end;
};

export interface Progress {
  origin: "lower" | "upper";
  other: "lower" | "upper";
  isResolution: boolean;
  oneHouse: boolean;
  introduced: string | null;
  committee: string | null;
  referred: string | null;
  hearing: string | null;
  committeeVote: string | null;
  committeeRecommended: boolean;
  passedOrigin: { date: string; tally: { yes: number; no: number } | null } | null;
  passedOther: { date: string; tally: { yes: number; no: number } | null } | null;
  presented: string | null;
  signed: string | null;
  act: string | null;
  vetoed: string | null;
  partialVeto: boolean;
  /** `voted` is false for the automatic "failed ... pursuant to Joint
   * Rule 82" entry, which records no vote. */
  override: { date: string; passed: boolean; voted: boolean } | null;
  sessionEnd: string | null;
}

export function progress(bill: StoryBill, actions: StoryAction[]): Progress {
  const origin = bill.chamber === "upper" ? "upper" : "lower";
  const other = origin === "upper" ? "lower" : "upper";
  const cls = bill.classification ?? "";
  const isResolution = cls.includes("resolution");
  const p: Progress = {
    origin, other, isResolution,
    oneHouse: isResolution && !cls.includes("joint"),
    introduced: actions[0]?.date ?? null,
    committee: null, referred: null, hearing: null, committeeVote: null,
    committeeRecommended: false,
    passedOrigin: null, passedOther: null, presented: null, signed: null, act: null,
    vetoed: null, partialVeto: false, override: null, sessionEnd: null,
  };
  for (const a of actions) {
    const d = a.description ?? "";
    const inOrigin = (a.chamber ?? origin) === origin;
    if (!p.passedOrigin && inOrigin) {
      // a bill withdrawn and re-referred moves to the new committee; once a
      // committee recommends it, later referrals (Rules) are scheduling
      if (!p.committeeRecommended && has(a, "referral-committee")) {
        const name = committeeFromReferral(d, a.chamber ?? origin);
        if (name) {
          p.committee = name;
          p.referred = a.date;
        }
      }
      if (!p.hearing && HEARING_RE.test(d)) p.hearing = a.date;
      const report = REPORT_RE.exec(d);
      if (report || has(a, "committee-passage-favorable")) {
        p.committeeVote = a.date;
        p.committeeRecommended = true;
      } else if (!p.committeeVote && EXEC_RE.test(d)) {
        p.committeeVote = a.date;
      }
    }
    if (has(a, "passage") && !OVERRIDE_RE.test(d)) {
      if (inOrigin && !p.passedOrigin) p.passedOrigin = { date: a.date, tally: tally(d) };
      else if (!inOrigin && !p.passedOther) p.passedOther = { date: a.date, tally: tally(d) };
    }
    if (PRESENTED_RE.test(d) || has(a, "executive-receipt")) p.presented ??= a.date;
    if (SIGNED_RE.test(d) || has(a, "executive-signature")) {
      p.signed ??= a.date;
      if (/partial veto/i.test(d)) p.partialVeto = true;
    }
    if (has(a, "executive-veto-line-item")) p.partialVeto = true;
    const act = ACT_RE.exec(d);
    if (act) p.act = `${act[1]} Wisconsin Act ${act[2]}`;
    if ((VETOED_RE.test(d) && !SIGNED_RE.test(d)) || has(a, "executive-veto")) p.vetoed ??= a.date;
    if (OVERRIDE_RE.test(d)) {
      p.override = { date: a.date, passed: !/^failed/i.test(d), voted: tally(d) != null || !/^failed/i.test(d) };
    }
    if (SJR1_RE.test(d)) p.sessionEnd ??= a.date;
  }
  return p;
}

export type StopKey = "introduced" | "committee" | "origin" | "other" | "governor" | "law" | "adopted";
export interface Stop {
  key: StopKey;
  label: string;
  state: "done" | "here" | "todo";
  /** A date or a short fact under a stop already passed. */
  detail?: string;
  /** The sentence beside the current stop. */
  note?: string;
}

export interface Story {
  headline: string;
  /** Plain sentences. Spans marked with [[term-id|text]] become terms. */
  body: string[];
  stops: Stop[];
  stopped: boolean;
  terms: TermId[];
  progress: Progress;
  /** The status the story tells: a one-house resolution that passed its
   * chamber is adopted. */
  status: string;
}

const article = (word: string) => (/^[AEIOU]/i.test(word) ? "an" : "a");
// short enough for a route column: the tally when there was one
const passedText = (v: { date: string; tally: { yes: number; no: number } | null }) =>
  v.tally ? `Passed ${v.tally.yes} to ${v.tally.no}` : `Passed ${fmtDate(v.date)}`;

export function tellStory(bill: StoryBill, actions: StoryAction[], today: string): Story {
  const p = progress(bill, actions);
  const raw = bill.status ?? "introduced";
  const status = p.oneHouse && raw === "passed_chamber" ? "adopted" : raw;
  const originName = chamberName(p.origin);
  const otherName = chamberName(p.other);
  const closed = sessionClosed(bill.session_id, today) || status === "failed_sjr1";
  const thing = p.isResolution ? "proposal" : "bill";
  const terms = new Set<TermId>();

  // ---- the route ----
  const keys: StopKey[] = p.isResolution
    ? ["introduced", ...(p.committee ? (["committee"] as StopKey[]) : []), "origin", ...(p.oneHouse ? [] : (["other"] as StopKey[])), "adopted"]
    : ["introduced", "committee", "origin", "other", "governor", "law"];
  const labels: Record<StopKey, string> = {
    introduced: "Introduced",
    committee: "Committee",
    origin: `${originName} vote`,
    other: `${otherName} vote`,
    governor: "Governor",
    law: "Law",
    adopted: "Adopted",
  };
  const doneByEvidence: Record<StopKey, boolean> = {
    introduced: true,
    committee: p.committeeRecommended || !!p.passedOrigin,
    origin: !!p.passedOrigin,
    other: !!p.passedOther,
    governor: !!p.signed,
    law: !!p.signed,
    adopted: status === "adopted",
  };
  // the derived status is authoritative when the history is thin
  const floor: Record<string, StopKey | null> = {
    passed_chamber: "origin",
    passed: "other",
    vetoed: "other",
    enacted: "law",
    adopted: "adopted",
  };
  const floorIdx = floor[status] ? keys.indexOf(floor[status]!) : -1;
  const done = keys.map((k, i) => doneByEvidence[k] || i <= floorIdx);
  // never mark a stop done after one that is not
  for (let i = 1; i < done.length; i++) if (!done[i - 1]) done[i] = false;
  let here = done.indexOf(false);
  const arrived = here === -1;
  if (arrived) here = keys.length - 1;
  const hereKey = keys[here];
  const vetoFinal = vetoWindowClosed(bill.session_id, today);
  // a veto can still be overridden until the veto-review days pass
  const stopped = !arrived && (status === "vetoed" ? vetoFinal : closed && status !== "passed");
  const overridden = !!p.override?.passed && !p.signed;

  const stopNote = (): string => {
    switch (hereKey) {
      case "introduced":
        return stopped ? "Stopped here. It was never sent to a committee." : "Waiting to be sent to a committee.";
      case "committee":
        if (stopped) {
          if (p.committeeVote) return "Stopped here. The committee didn't recommend it.";
          return p.hearing
            ? "Stopped here. It had a hearing but no committee vote."
            : "Stopped here. No public hearing was held.";
        }
        return p.hearing ? "Had a hearing. Waiting for a committee vote." : "Waiting for a public hearing.";
      case "origin":
        return stopped ? `Stopped here. The full ${originName} never voted on it.` : `Waiting for a vote by the full ${originName}.`;
      case "other":
        return stopped ? `Stopped here. The ${otherName} never voted on it.` : `Waiting for the ${otherName}.`;
      case "governor":
        if (p.vetoed || status === "vetoed") return `Vetoed${p.vetoed ? ` ${fmtDate(p.vetoed)}` : ""}.`;
        return stopped ? "Stopped here. It never went to the governor." : "Waiting for a decision.";
      case "law":
        // keep "Act 1" together in a narrow route column
        return p.act?.replace(/ (\d+)$/, "\u00a0$1") ?? "Became law.";
      case "adopted":
        return "Resolutions end here.";
    }
  };
  const detailFor = (k: StopKey): string | undefined => {
    switch (k) {
      case "introduced":
        return p.introduced ? fmtDate(p.introduced) : undefined;
      case "committee":
        return p.committeeRecommended ? "Approved" : undefined;
      case "origin":
        return p.passedOrigin ? passedText(p.passedOrigin) : undefined;
      case "other":
        return p.passedOther ? passedText(p.passedOther) : undefined;
      case "governor":
        return p.signed ? "Signed" : overridden ? "Veto overridden" : undefined;
      default:
        return undefined;
    }
  };
  const stops: Stop[] = keys.map((k, i) => ({
    key: k,
    label: labels[k],
    state: i === here ? "here" : done[i] ? "done" : "todo",
    detail: i === here ? undefined : done[i] ? detailFor(k) : undefined,
    note: i === here ? stopNote() : undefined,
  }));

  // ---- the headline and what to say under it ----
  const committee = p.committee ? `the ${p.committee}` : "a committee";
  const lastDay = lastVotingDay(bill.session_id);
  const lastDayLine = lastDay ? `The last day for votes this session was ${fmtDate(lastDay)}.` : "";
  const tryAgain = `To try again, a lawmaker would have to start a new ${thing}.`;
  let headline: string;
  let body: string[];
  if (status === "enacted") {
    headline = "Became law";
    terms.add("act");
    const actLine = p.act ? ` It's [[act|${p.act}]].` : "";
    if (overridden) {
      terms.add("veto-override");
      body = [`The governor vetoed it, and lawmakers [[veto-override|overrode the veto]] on ${fmtDate(p.override!.date)}, so it became law.${actLine}`];
    } else {
      body = [`The governor signed it${p.signed ? ` on ${fmtDate(p.signed)}` : ""}.${actLine}`];
    }
    if (p.partialVeto) {
      terms.add("partial-veto");
      body.push("Before signing, the governor struck some parts using Wisconsin's [[partial-veto|partial veto]].");
    }
  } else if (status === "adopted") {
    headline = "Adopted";
    const lastVote = p.passedOther?.date ?? p.passedOrigin?.date;
    if (p.oneHouse) {
      body = [`The ${originName} adopted it${lastVote ? ` on ${fmtDate(lastVote)}` : ""}. Resolutions don't go to the governor.`];
    } else {
      terms.add("joint-resolution");
      body = [`Both chambers adopted it${lastVote ? `, the second on ${fmtDate(lastVote)}` : ""}. A [[joint-resolution|joint resolution]] doesn't go to the governor.`];
    }
  } else if (status === "vetoed") {
    headline = "Vetoed by the governor";
    body = [`Both chambers passed it, and the governor vetoed it${p.vetoed ? ` on ${fmtDate(p.vetoed)}` : ""}.`];
    terms.add("veto-override");
    if (p.override && !p.override.passed && p.override.voted) {
      body.push(`Lawmakers tried to [[veto-override|override the veto]] on ${fmtDate(p.override.date)}, but fell short of the two-thirds it takes.`);
    } else if (!vetoFinal) {
      body.push("Lawmakers can still [[veto-override|override the veto]] with a two-thirds vote in each chamber.");
    } else {
      body.push("Lawmakers did not [[veto-override|override the veto]], so it stands.");
    }
  } else if (status === "passed") {
    headline = "Waiting for the governor";
    body = ["Both chambers passed it. The governor can sign it into law or veto it."];
  } else if (hereKey === "governor") {
    // both chambers passed it, but it never reached the governor
    terms.add("second-chamber");
    headline = stopped ? "Passed both chambers, then stopped" : "Passed both chambers";
    body = stopped
      ? [
          `The ${originName} and the ${otherName} both voted to pass it, but it never went to the governor. A bill goes to the governor only after both chambers [[second-chamber|pass the same version]].`,
          lastDayLine,
          tryAgain,
        ]
      : [`Both chambers voted to pass it. It goes to the governor once both have [[second-chamber|passed the same version]].`];
  } else if (hereKey === "other") {
    terms.add("second-chamber");
    if (stopped) {
      headline = `Passed the ${originName}, then stopped`;
      body = [
        `The ${originName} passed it${p.passedOrigin ? ` on ${fmtDate(p.passedOrigin.date)}` : ""}, but the ${otherName} never voted on it. A bill has to [[second-chamber|pass both chambers]].`,
        lastDayLine,
        tryAgain,
      ];
    } else {
      headline = `Passed the ${originName}`;
      body = [`It's waiting for the ${otherName}. A bill has to [[second-chamber|pass both chambers]] before it goes to the governor.`];
    }
  } else if (hereKey === "origin") {
    if (stopped) {
      headline = `Stopped before the full ${originName} voted`;
      body = [
        p.committeeRecommended
          ? `The [[committee|committee]] recommended passing it, but the full ${originName} never voted on it.`
          : `The full ${originName} never voted on it.`,
        lastDayLine,
        tryAgain,
      ];
    } else {
      headline = `Waiting for ${article(originName)} ${originName} vote`;
      body = [
        p.committeeRecommended
          ? `The [[committee|committee]] recommended passing it. Next, the full ${originName} votes on it.`
          : `Next, the full ${originName} votes on it.`,
      ];
    }
    terms.add("committee");
  } else if (hereKey === "introduced") {
    headline = stopped ? "Stopped after it was introduced" : "Introduced";
    body = stopped
      ? ["It was never sent to a committee, so it never came up for a vote.", lastDayLine, tryAgain]
      : ["It hasn't been sent to a committee yet."];
  } else {
    // in committee
    terms.add("committee");
    terms.add("public-hearing");
    if (stopped) {
      headline = "Stopped in committee";
      body = [
        p.committeeVote
          ? `The [[committee|committee]] voted on it but didn't recommend it, so the full ${originName} never voted.`
          : p.hearing
            ? "It had a [[public-hearing|public hearing]] but no committee vote, so it never came up for a vote."
            : "It never got a [[public-hearing|public hearing]], so it never came up for a vote.",
        lastDayLine,
        tryAgain,
      ];
    } else {
      headline = "Waiting in committee";
      body = [
        p.hearing
          ? `${cap(committee)} held a [[public-hearing|public hearing]] on ${fmtDate(p.hearing)}. Next, the committee decides whether to vote on it.`
          : `${cap(committee)} has it. It needs a [[public-hearing|public hearing]] before it can move.`,
      ];
    }
  }
  if (p.sessionEnd || SJR1_RE.test(actions.at(-1)?.description ?? "")) terms.add("sjr1");
  return { headline, body: body.filter(Boolean), stops, stopped, terms: [...terms], progress: p, status };
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Split "[[id|text]]" markers into text and term runs for rendering. */
export const termRuns = (text: string): ({ text: string } | { term: TermId; text: string })[] => {
  const runs: ({ text: string } | { term: TermId; text: string })[] = [];
  const re = /\[\[([a-z0-9-]+)\|([^\]]+)\]\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) runs.push({ text: text.slice(last, m.index) });
    runs.push({ term: m[1] as TermId, text: m[2] });
    last = m.index! + m[0].length;
  }
  if (last < text.length) runs.push({ text: text.slice(last) });
  return runs;
};

// ---- the history, in plain sentences ----

export interface HistoryEvent {
  /** "Mar 23, 2026", or a range for grouped sign-ons. */
  when: string;
  date: string;
  text: string;
  /** The Legislature's wording, shown when we have no plain version. */
  official?: boolean;
}

type Plain = { text: string; official?: boolean } | { signOn: "representative" | "senator"; count: number } | null;

// Floor and clerk housekeeping. Every one of these is still in the
// official record below the plain list.
const MINOR_RE = new RegExp(
  [
    "^read first time$", "^read a second time", "^ordered to a third reading", "^rules suspended",
    "^ordered immediately messaged", "^available for scheduling", "^placed on calendar",
    "^report correctly enrolled", "^lrb correction", "^received from (?:assembly|senate) (?:concurred|amended)",
    "^(?:assembly|senate) (?:substitute )?amendment", "^laid on (?:the )?table", "^taken from (?:the )?table",
    "^made a special order", "^withdrawn from committee", "^refused to", "^decision of the chair",
    "^ordered to the calendar",
    "^read and referred to calendar", "^referred to calendar", "^report (?:received|without recommendation)",
    "^representative .+ withdrawn as", "^senator .+ withdrawn as", "^enrolled joint resolution",
    "^deposited in the office of the secretary of state",
    "^report (?:assembly|senate) (?:substitute )?amendment", "^report introduction and adoption of",
  ].join("|"),
  "i",
);

function plainAction(a: StoryAction, origin: string, thing: string, hasReport: boolean): Plain {
  const d = (a.description ?? "").trim();
  const ch = chamberName(a.chamber);
  let m: RegExpExecArray | null;
  const signOn = /^(?:representatives?|senators?) (.+?) added as (?:a )?(?:coauthor|cosponsor)s?$/i.exec(d);
  if (signOn) {
    // "Representatives Smith and Jones added as coauthors" is two people
    const count = signOn[1].split(/,\s*(?:and\s+)?|\s+and\s+/).filter(Boolean).length;
    return { signOn: /^senator/i.test(d) ? "senator" : "representative", count };
  }
  if (/^introduced by\b/i.test(d)) return { text: `Introduced in the ${ch}.` };
  if (/^received from (assembly|senate)\s*$/i.test(d)) return { text: `The ${ch} received it.` };
  if ((m = REPORT_RE.exec(d))) {
    const verb = /adoption/i.test(m[1]) ? "adopting" : "passing";
    const t = m[3] ? `, ${m[3]} to ${m[4]}` : "";
    return { text: `The committee voted to recommend ${verb} it${t}.` };
  }
  if (has(a, "referral-committee") || /\breferred to\b/i.test(d)) {
    const name = committeeFromReferral(d, a.chamber);
    if (name) return { text: `Sent to the ${name}.` };
  }
  if (HEARING_RE.test(d)) return { text: "The committee held a public hearing." };
  // the committee's report says how it voted; without one, say it voted
  if (EXEC_RE.test(d)) return hasReport ? null : { text: "The committee voted on it." };
  if (SJR1_RE.test(d)) return { text: `The session ended, and the ${thing} died with it.` };
  if (OVERRIDE_RE.test(d)) {
    const t = tally(d);
    if (/^failed/i.test(d)) {
      // with no tally this is the automatic end of the override window
      return t
        ? { text: `The ${ch} tried to override the veto, ${t.yes} to ${t.no}, short of the two-thirds it takes.` }
        : { text: "The veto stood. Lawmakers didn't override it." };
    }
    return { text: `The ${ch} voted to override the veto${t ? `, ${t.yes} to ${t.no}` : ""}.` };
  }
  if (/^read a third time and passed|^passed\b/i.test(d) || (has(a, "passage") && /passed/i.test(d))) {
    const t = tally(d);
    return { text: `The ${ch} passed it${t ? `, ${t.yes} to ${t.no}` : ""}.` };
  }
  if (/(?<!non)concurred in/i.test(d) && (a.chamber ?? origin) !== origin) {
    const t = tally(d);
    const verb = thing === "proposal" ? "adopted" : "passed";
    return { text: `The ${ch} ${verb} it too${t ? `, ${t.yes} to ${t.no}` : ""}.` };
  }
  if (/^adopted\b/i.test(d) || (has(a, "passage") && /adopt/i.test(d))) {
    const t = tally(d);
    return { text: `The ${ch} adopted it${t ? `, ${t.yes} to ${t.no}` : ""}.` };
  }
  if (PRESENTED_RE.test(d)) return { text: "Sent to the governor." };
  if (SIGNED_RE.test(d)) {
    const act = ACT_RE.exec(d);
    const law = act ? ` It became ${act[1]} Wisconsin Act ${act[2]}.` : "";
    return /partial veto/i.test(d)
      ? { text: `The governor signed it after striking some parts with a partial veto.${law}` }
      : { text: `The governor signed it.${law}` };
  }
  if (VETOED_RE.test(d)) return { text: "The governor vetoed it." };
  if (/^published\b/i.test(d)) return { text: "The new law was published." };
  if (/^fiscal estimate received/i.test(d)) return { text: "A state agency sent in its estimate of the cost." };
  if (MINOR_RE.test(d)) return null;
  return { text: d, official: true };
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Newest first. Runs of sign-ons collapse into one line. */
export function plainHistory(bill: StoryBill, actions: StoryAction[]): HistoryEvent[] {
  const origin = bill.chamber === "upper" ? "upper" : "lower";
  const thing = (bill.classification ?? "").includes("resolution") ? "proposal" : "bill";
  const out: HistoryEvent[] = [];
  const hasReport = actions.some((a) => REPORT_RE.test(a.description ?? ""));
  let run: { first: string; last: string; reps: number; sens: number } | null = null;
  const flush = () => {
    if (!run) return;
    const parts = [
      run.reps ? plural(run.reps, "more representative", "more representatives") : "",
      run.sens ? plural(run.sens, run.reps ? "senator" : "more senator", run.reps ? "senators" : "more senators") : "",
    ].filter(Boolean);
    const when = run.first === run.last ? fmtDate(run.first) : `${fmtDate(run.first)} to ${fmtDate(run.last)}`;
    out.push({ when, date: run.last, text: `${parts.join(" and ")} signed on in support.` });
    run = null;
  };
  for (const a of actions) {
    const plain = plainAction(a, origin, thing, hasReport);
    if (!plain) continue;
    if ("signOn" in plain) {
      run ??= { first: a.date, last: a.date, reps: 0, sens: 0 };
      run.last = a.date;
      if (plain.signOn === "senator") run.sens += plain.count;
      else run.reps += plain.count;
      continue;
    }
    flush();
    const prev = out.at(-1);
    // the same plain sentence on the same day is one event
    if (prev && prev.date === a.date && prev.text === plain.text) continue;
    out.push({ when: fmtDate(a.date), date: a.date, text: plain.text, official: plain.official });
  }
  flush();
  return out.reverse();
}
